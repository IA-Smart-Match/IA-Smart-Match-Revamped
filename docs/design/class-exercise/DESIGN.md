# Class exercise visual refresh — design system

**Status:** Proposed. Docs only; no app code changes with this file.
**Scope:** the no-login class exercise under
`apps/web/legacy-frontend/src/app/pages/exercise/` (routes `/exercise/*`).
**Parent contract:** [`apps/web/DESIGN.md`](../../../apps/web/DESIGN.md). That
file stays authoritative for brand, voice, provenance and accessibility. This
file is a scoped extension: it adds exercise-only aliases, motion, and layouts.
On any conflict, `apps/web/DESIGN.md` wins, then the API contract.
**Tokens source:** [`theme.css`](../../../apps/web/legacy-frontend/src/styles/theme.css)
and [`fonts.css`](../../../apps/web/legacy-frontend/src/styles/fonts.css).
Every `--ce-*` token below is an alias of an existing value or a tint or
shade of an existing CPP hue. No new brand colour is introduced.
**Last updated:** 2026-09-25

Companion files:

- [`prompts/README.md`](../../archive/design/class-exercise/prompts/README.md): how to generate screens from this system.
- [`experiments.md`](experiments.md): directions explored and why this one won.
- [`generated.md`](../../archive/design/class-exercise/generated.md): contact sheet of the 2026-09-26 mock-ups (24 images and a private Claude Design canvas).
- [`assets/svg/`](assets/svg): the spot art this system allows.
- [`assets/mockups/`](../../archive/design/class-exercise/assets/mockups): 8 reference PNGs from the Fable
  experimental track ("The Room" and "The Ledger"). They show layout and
  motion intent; their teal palette and Fraunces/Newsreader type are **not**
  this system's. Where they differ, this file wins.

---

## 1. Principles

1. **The room reads it first.** Every screen is projected in a lit classroom
   and read from the back row. Size, contrast and one clear focal point beat
   density. Body text is 20px on desktop; nothing that carries data is under 16px.
2. **Counts, never scores.** ADR-0025 D8 holds everywhere: no percentage,
   confidence, match strength, progress-to-threshold, or bar that reads like
   one. Rank is a position. Weights are the team's own input and may be shown.
3. **The server's words, verbatim.** Reason lines, refusals, factor labels and
   the license line are rendered exactly as sent. Styling may frame a sentence;
   it may not split, re-case, truncate or re-word it.
4. **Warm paper, green ink.** The surface is CPP Eggwhite "card stock"; action
   and identity are CPP Green; CPP Gold is a highlighter used for at most one
   thing per screen. Warmth comes from material, type and motion, not from
   more colours.
5. **Motion explains cause and effect.** A slider moves, the list re-sorts. A
   team runs results, the seats fill. One authored moment (the results reveal)
   per flow; everything else is fast feedback. Reduced motion keeps meaning.
6. **Refusals are calm states.** "The instructor has not opened results yet"
   is the product working. It gets a composed panel, never a red alert.

## 2. Brand and aesthetic evolution

### Before (origin/main, 2026-09-25)

| Trait | What ships today | Why it reads "barebone and industrialized" |
|---|---|---|
| Colour | Tailwind `slate-*` greys, `amber-*` for overlap, black selected tiles | Ignores the CPP tokens the rest of the app uses; reads as a wireframe |
| Surfaces | `border-2 border-slate-400` boxes on white, no elevation | Every element is the same weight; nothing leads |
| Type | One sans at `text-xl`/`text-3xl`; no Transducer or Proxima Sera roles applied beyond the base `h1`/`h2` families | Hierarchy by size only; no voice |
| Controls | Weights are 160px text boxes; choices are grey outlined buttons | Feels like a form, not a decision |
| Results | Three grey figure boxes and a Recharts chart in off-brand blue, green and brown | The lesson's payoff has no moment |
| Motion | None (`isAnimationActive={false}` on the chart) | State changes snap; the list re-sort is invisible |
| States | "Loading the list…" as text; refusals in grey boxes | Honest, but inert |

### After (this system)

| Trait | Direction |
|---|---|
| World | **The invitation desk.** The team is promoting a campus career event with 60 seats. The visual world is that event's stationery: RSVP cards, place cards, a seating chart, a highlighter. It is the class's own marketing task made tangible. |
| Colour | Eggwhite page (`#F8F6F1`), white card stock, CPP Green ink and actions, Gold as highlighter (overlap, the chosen card, "your" seats' legend), Bay Brown for seats that were already taken and for paper edges. |
| Surfaces | White cards with a soft two-layer shadow and no border. Controls keep a 3:1 outline. Nesting stops at one level. |
| Type | Transducer CPP for the page title and big numerals (ranks, seat figures); Proxima Sera for section heads and reason lines, like a margin note; Usual for everything a hand operates. |
| Controls | Four real sliders with a paired numeric field; team tiles like numbered place cards; the three asking choices as full cards. |
| Results | A 60-seat seating chart that fills in: taken seats, then the team's additions, then the open seats and one plain sentence. |
| Motion | A small named vocabulary (section 5), each with a reduced-motion path. |
| States | Skeletons shaped like the content; refusals as composed panels with one spot illustration and the server's sentence. |

What does **not** change: the CPP logo rules, the five brand hues, the three
font roles, sentence case, the no-score rule, and the "not now" line in Ann's
build table (no mobile app; no CPP colours or styling beyond what already
exists). This refresh restyles with existing brand material only.

## 3. Tokens

All tokens are CSS custom properties under `:root`, with dark values under
`.dark` (the app's existing class strategy). Names use the `--ce-` prefix so
they cannot collide with CBA screens. Implementation maps them onto the
`theme.css` variables named in the "Alias of" column.

### 3.1 Colour — light

| Token | Value | Alias of | Use | Contrast (checked) |
|---|---|---|---|---|
| `--ce-page` | `#F8F6F1` | `--background` | Page background | — |
| `--ce-surface` | `#FFFFFF` | `--card` | Cards, table body, sheets | — |
| `--ce-surface-sunk` | `#F2EEE8` | `--cpp-eggwhite` / `--muted` | Wells, table header band, skeleton base | — |
| `--ce-ink` | `#163229` | `--foreground` | Body and headings | 12.8:1 on page, 13.8:1 on surface |
| `--ce-ink-muted` | `#59665F` | `--muted-foreground` | Secondary text, reason lines | 5.6:1 on page, 5.2:1 on sunk |
| `--ce-primary` | `#005030` | `--primary` / `--cpp-green` | Primary action, focus ring, rank numerals, "your" seats | 9.6:1 on surface |
| `--ce-on-primary` | `#FFFFFF` | `--primary-foreground` | Text on primary | 9.6:1 |
| `--ce-primary-tint` | `#D9EADF` | `--primary-container` | Selected row, selected tile fill | ink 9.9:1 on it (`#003D24`) |
| `--ce-gold` | `#FFB81C` | `--cpp-gold` / `--secondary` | Highlighter fill: overlap tag, chosen-card seal | text `#17352A` 7.7:1 on it |
| `--ce-gold-tint` | `#FFF1CC` | tint of `--cpp-gold` | Overlap row wash, "joined the list" flash | ink 12.3:1 |
| `--ce-gold-ink` | `#7A5200` | shade of `--cpp-gold` | Gold-coded text and strokes on light surfaces | 6.9:1 on surface, 6.2:1 on gold tint |
| `--ce-avocado` | `#A4D65E` | `--cpp-avocado` | Decorative accent only (never text, never sole signal) | 1.7:1, decorative |
| `--ce-avocado-tint` | `#E8F2D8` | `--accent` | Success wash behind a confirmed state | ink 11.9:1 |
| `--ce-bay` | `#CFBAB0` | `--cpp-bay-brown` | Decorative paper edges, dividers | 1.9:1, decorative |
| `--ce-seat-taken` | `#8C6D62` | `--chart-4` | "Already coming" seats | 4.7:1 on surface |
| `--ce-line` | `#D9CBC4` | `--border` | Decorative dividers only | 1.6:1, decorative |
| `--ce-line-strong` | `#8F7A70` | shade of `--cpp-bay-brown` | Control outlines, open-seat outline, slider track | 3.8:1 on page |
| `--ce-danger` | `#BA1A1A` | `--destructive` | Transport errors, destructive confirm | 6.5:1 on surface |
| `--ce-scrim` | `rgba(16,37,29,0.48)` | from `--background` dark | Behind a sheet on 390 | — |

### 3.2 Colour — dark

Dark mode exists for a dimmed room and for instructors who run the OS in dark.
Light is the default for projection.

| Token | Value | Alias of | Contrast (checked) |
|---|---|---|---|
| `--ce-page` | `#10251D` | `.dark --background` | — |
| `--ce-surface` | `#173228` | `.dark --card` | — |
| `--ce-surface-sunk` | `#244237` | `.dark --muted` | — |
| `--ce-ink` | `#F2EEE8` | `.dark --foreground` | 11.9:1 on surface |
| `--ce-ink-muted` | `#CFC5BE` | `.dark --muted-foreground` | 8.1:1 on surface |
| `--ce-primary` | `#A4D65E` | `.dark --primary` | 9.5:1 on page |
| `--ce-on-primary` | `#10251D` | `.dark --primary-foreground` | 9.5:1 |
| `--ce-primary-tint` | `#315343` | `.dark --accent` | ink 7.6:1 |
| `--ce-gold` | `#FFB81C` | `.dark --secondary` | 8.0:1 on surface |
| `--ce-gold-tint` | `#3A3420` | shade of gold | ink 10.9:1 |
| `--ce-gold-ink` | `#FFD37A` | tint of gold | 9.8:1 on surface |
| `--ce-seat-taken` | `#B89A8E` | tint of bay brown | 5.3:1 on surface |
| `--ce-line` | `#496257` | `.dark --border` | decorative |
| `--ce-line-strong` | `#8FA89C` | tint of `.dark --border` | 5.4:1 on surface |
| `--ce-danger` | `#FFB4AB` | `.dark --destructive` | 8.1:1 on surface |

### 3.3 Chart and seat colours

| Series | Light fill / stroke | Dark fill / stroke | Non-colour cue |
|---|---|---|---|
| Invited | `#D9EADF` / `#005030` 2px | `#315343` / `#A4D65E` 2px | Open (unhatched) bar |
| Signed up | `#FFB81C` / `#7A5200` 2px | `#FFB81C` / `#FFD37A` 2px | 45° hatch |
| Attended | `#005030` / `#005030` | `#A4D65E` / `#A4D65E` | Solid bar |
| Seat — already coming | `--ce-seat-taken` fill | same token | Filled square, no mark |
| Seat — your team added | `--ce-primary` fill | same token | Filled square with a 2px inner check stroke in `--ce-on-primary` |
| Seat — still open | transparent, 2px `--ce-line-strong` outline | same token | Outline only |

Every bar carries a direct numeric label; every seat chart carries a legend
and the sentence form of the same numbers.

### 3.4 Type

Families come from `fonts.css`. Fallbacks are the ones already declared there.

| Token | Family | Weight | Desktop size/line | 390 size/line | Tracking | Use |
|---|---|---|---|---|---|---|
| `--ce-type-display` | Transducer CPP | 700 | 72/76 | 48/52 | 0 | Seat figures, points total |
| `--ce-type-h1` | Transducer CPP | 600 | 48/56 | 32/38 | 0 | The one page title |
| `--ce-type-h2` | Proxima Sera | 600 | 32/40 | 26/32 | -0.01em | Section heads |
| `--ce-type-h3` | Proxima Sera | 600 | 24/32 | 21/28 | -0.01em | Card titles, sub-sections |
| `--ce-type-lead` | Usual | 400 | 22/34 | 18/28 | 0 | Intro line under `h1` |
| `--ce-type-body` | Usual | 400 | 20/30 | 17/26 | 0 | Body, table cells |
| `--ce-type-reason` | Proxima Sera | 400 | 18/28 | 16/24 | 0 | Reason line under a name |
| `--ce-type-label` | Usual | 600 | 18/24 | 16/22 | 0.01em | Control labels, column heads |
| `--ce-type-meta` | Usual | 500 | 16/24 | 15/22 | 0.01em | Helper text only, never data |
| `--ce-type-rank` | Transducer CPP | 700 | 28/32 | 22/26 | 0 | Rank numerals |
| `--ce-type-value` | Usual | 700 | 22/28 | 18/24 | 0 | Slider value, counts in cards |

Rules:

- All numerals in tables, ranks, weights, counts and seats use
  `font-variant-numeric: tabular-nums`.
- Column heads are sentence case at `--ce-type-label`. No uppercase tracking
  bands (the current `uppercase tracking-wide` heads are retired).
- Line length for prose: 60–72ch. Tables may run wider.
- If Adobe Fonts is blocked, the fallbacks (Arial Narrow, Georgia, Inter)
  must keep the hierarchy. Check the matching screen with fonts blocked.
- Mock-up tools cannot load the licensed faces. Prompts use stand-ins:
  **Archivo SemiExpanded** for Transducer, **Source Serif 4** for Proxima
  Sera, **Figtree** for Usual. These are for mock-ups only; production keeps
  the licensed faces.

### 3.5 Spacing

4px base. Use only these steps.

| Token | px | Typical use |
|---|---|---|
| `--ce-space-1` | 4 | Icon-to-label gap |
| `--ce-space-2` | 8 | Chip padding, tight groups |
| `--ce-space-3` | 12 | Row inner gap |
| `--ce-space-4` | 16 | Card padding on 390, gutter on 390 |
| `--ce-space-5` | 24 | Card padding on desktop, gap between related cards |
| `--ce-space-6` | 32 | Gap between sections on 390 |
| `--ce-space-7` | 48 | Gap between sections on desktop |
| `--ce-space-8` | 64 | Page top padding on desktop |
| `--ce-space-9` | 96 | Opening screen breathing room |

More space above a heading than below it: `h2` gets `--ce-space-7` above and
`--ce-space-4` below on desktop.

### 3.6 Radius

| Token | Value | Use |
|---|---|---|
| `--ce-radius-seat` | 4px | Seat squares |
| `--ce-radius-control` | 10px (`--radius-sm`) | Inputs, buttons, slider thumb housing |
| `--ce-radius-card` | 14px (`--radius-lg`) | Cards, panels, tiles |
| `--ce-radius-sheet` | 18px (`--radius-xl`) | Mobile sheet top corners |
| `--ce-radius-pill` | 999px | Chips and tags only |

### 3.7 Elevation

Declare elevation once: a card has a shadow **or** a border, never both.

| Token | Value | Use |
|---|---|---|
| `--ce-elev-0` | none | Flat rows inside a card |
| `--ce-elev-1` | `0 1px 2px rgba(22,50,41,.06), 0 4px 12px rgba(22,50,41,.06)` | Resting card |
| `--ce-elev-2` | `0 2px 4px rgba(22,50,41,.06), 0 12px 28px rgba(0,80,48,.10)` | Hovered card, selected card |
| `--ce-elev-3` | `0 8px 16px rgba(22,50,41,.08), 0 24px 60px rgba(0,80,48,.16)` | Sheet, sticky bar |
| Dark mode | same offsets, colour `rgba(0,0,0,.35)` | — |

### 3.8 Layout grid

| Width | Columns | Gutter | Max content | Side margin |
|---|---|---|---|---|
| 1280 | 12 | 24 | 1152 | 64 |
| 1024 | 12 | 24 | 944 | 40 |
| 768 | 8 | 20 | 704 | 32 |
| 390 | 4 | 16 | 358 | 16 |

No horizontal page scroll at any width. Touch targets are at least 44×44px.

### 3.9 Browser surfaces

- Focus ring: 3px `--ce-primary` outline, 3px offset, on every focusable thing.
- Text selection: `--ce-gold-tint` background, `--ce-ink` text.
- Caret: `--ce-primary`.
- Link underline: 1px, offset 4px, `--ce-primary`; 2px on hover.
- Scrollbars inside wide tables: thin, thumb `--ce-line-strong`, track `--ce-surface-sunk`.

## 4. Iconography and illustration

- **Icons:** `lucide-react` only, stroke 2, sizes 20 / 24 / 32. Colour by
  `currentColor`. Icons sit inside actions, states, chips and legends. No icon
  beside a page `h1` (parent contract rule).
- **Allowed icons by meaning:** `Users` (team), `CalendarDays` (event),
  `SlidersHorizontal` (weights), `ListOrdered` (the list), `Bookmark` (saved
  setting), `Columns2` (compare), `Link2` (on both lists), `Lock` / `LockOpen`
  (results lock), `Armchair` (seats), `Mail` (invite), `MessageSquareText`
  (asking), `Info` (notice), `TriangleAlert` (transport error), `Upload`,
  `FileSpreadsheet`, `KeyRound` (passcode), `RotateCcw` (reset), `Download`.
- **Spot art:** the geometric SVGs in [`assets/svg/`](assets/svg). They are
  shapes, not pictures, coloured by `currentColor` and drawn at 96–160px.
  Only in empty, locked and first-visit states; at most one per screen; never
  in a data row or next to a heading.

| Asset | Where |
|---|---|
| [`lecture-hall.svg`](assets/svg/lecture-hall.svg) | Opening screen, beside the license block (desktop only) |
| [`invitation-envelope.svg`](assets/svg/invitation-envelope.svg) | Results locked state |
| [`empty-state.svg`](assets/svg/empty-state.svg) | Empty saved-setting slot, empty list |
| [`profile-card.svg`](assets/svg/profile-card.svg) | Final-setting step when no setting is saved |
| [`partly-known-card.svg`](assets/svg/partly-known-card.svg) | Asking-for-more header |
| [`round-journey.svg`](assets/svg/round-journey.svg) | Round-two results, above the three-panel comparison |
| [`team-badge.svg`](assets/svg/team-badge.svg) | Team entry, "this browser is already in team 4" line |

- **No** emoji, no confetti, no people illustrations, no photographs of
  students, no stock imagery. `canvas-confetti` is installed; it stays unused
  here, because a results run is evidence to discuss, not a win.

## 5. Motion system

Library: `motion` 12.23 (installed). CSS transitions for simple state; Motion's
`layout` for list re-order; `animate()` for counters. Every motion has a
reduced-motion path via `useReducedMotion()` or
`@media (prefers-reduced-motion: reduce)`.

Easing tokens:

| Token | Value | Use |
|---|---|---|
| `--ce-ease-out` | `cubic-bezier(0.16, 1, 0.3, 1)` | Arrivals |
| `--ce-ease-in-out` | `cubic-bezier(0.65, 0, 0.35, 1)` | Moves between two resting states |
| `--ce-ease-exit` | `cubic-bezier(0.7, 0, 0.84, 0)` | Departures |
| `--ce-spring-row` | spring, stiffness 500, damping 40 (≈280ms settle) | List re-order |

Named motions:

| Name | What moves | Duration | Easing | Reduced motion |
|---|---|---|---|---|
| `ce-press` | Button or tile scales to 0.98 on press | 100ms | `--ce-ease-out` | Colour change only |
| `ce-lift` | Hoverable card: translateY(-2px), `elev-1`→`elev-2` | 160ms | `--ce-ease-out` | Shadow change only |
| `ce-fade-rise` | Section or panel enters: opacity 0→1, y 8→0 | 240ms | `--ce-ease-out` | Opacity 150ms |
| `ce-row-reorder` | Ranked rows slide to new positions after a weight commit | spring ≈280ms | `--ce-spring-row` | Instant move plus 150ms crossfade |
| `ce-row-join` | A name new to the list: gold-tint wash that fades out | 900ms (wash), row enters 200ms | `--ce-ease-out` | Static gold-tint for 900ms, then removed |
| `ce-row-leave` | A name leaving the list: opacity to 0, height collapse via layout | 140ms | `--ce-ease-exit` | Instant removal |
| `ce-slider-settle` | Thumb glides to a clicked track point; value readout ticks | 180ms | `--ce-ease-out` | Jump |
| `ce-list-rebuilding` | List dims to 0.6 while a new list is fetched; "Rebuilding the list…" status | 150ms in, 150ms out | linear | Same (opacity is not movement) |
| `ce-card-save` | New saved-setting card: scale 0.96→1, opacity 0→1 | 220ms | `--ce-ease-out` | Opacity 150ms |
| `ce-overlap-pulse` | On opening a comparison, each "on both lists" row pulses its gold wash once, 30ms stagger, total ≤600ms | 600ms | `--ce-ease-in-out` | Static gold wash, no pulse |
| `ce-confirm-window` | Asking card's button label swaps to "Confirm: …?"; a 2px underline shrinks from full width to 0 over the 5s window | 150ms swap, 5000ms linear underline | `--ce-ease-out` / linear | Label swap only; static "5 seconds" helper |
| `ce-choice-commit` | Chosen asking card fills `primary-tint` and shows the seal; others fade to 0.55 | 240ms | `--ce-ease-out` | Same end state, 150ms opacity |
| `ce-unlock` | Lock glyph shackle lifts 4px and swaps to `LockOpen`; panel background crossfades | 300ms | `--ce-ease-out` | Icon swap, no movement |
| `ce-seat-fill` | **The focal moment.** See 5.1 | ≤1.8s total | see 5.1 | Final state at once |
| `ce-count-up` | Seat figures and points count from 0 to value | 700ms | `--ce-ease-out` | Final number at once |
| `ce-skeleton` | Skeleton blocks breathe opacity 0.55↔1 | 1.6s loop | `--ce-ease-in-out` | Static at 0.75 |
| `ce-notice-in` | Notice panel enters: opacity + y 4→0 | 200ms | `--ce-ease-out` | Opacity 150ms |
| `ce-view` | Route change: crossfade via View Transitions API where supported | 220ms | `--ce-ease-in-out` | None |

Rules:

- Motion never blocks input. A re-order in flight is interrupted by the next commit.
- Exits are faster than entrances.
- No motion loops on screen except `ce-skeleton`, which stops when content lands.
- Count-ups run once per mount. Never re-run on re-render.
- The chart keeps `isAnimationActive={false}`: bars appear at full height. The
  seat chart carries the moment; two competing reveals would blur it.

### 5.1 The focal moment: `ce-seat-fill`

Trigger: results render for the first time after "Run results for this event"
succeeds (not on later visits, which show the final state).

| Step | Time | What happens |
|---|---|---|
| 1 | 0–240ms | Seating chart fades in with all 60 seats as open outlines |
| 2 | 240–600ms | The 8 "already coming" seats fill `--ce-seat-taken`, 12ms stagger, front row first. Line 1 fades in: "8 were already coming." |
| 3 | 700–1300ms | The team's 6 seats fill `--ce-primary`, 60ms stagger, each with a 1→1.08→1 scale. Line 2: "Your invitations added 6." |
| 4 | 1400–1800ms | The 46 open seats stay outlined; their outline brightens once. Line 3: "46 seats are still open." Figures count up (`ce-count-up`). |

Reduced motion: all seats in final state, the three lines and figures appear
together with a 150ms opacity fade. The `aria-live="polite"` region announces
the three sentences once, after step 4 (or immediately in reduced motion).

## 6. Component inventory

States: **D** default, **H** hover, **F** focus, **L** loading, **E** empty,
**X** error/refusal, **Dis** disabled. "n/a" means the state cannot occur;
say why in the component's prompt.

### 6.1 Screen shell (`ExerciseScreen`)

Header: CPP logo (compact, left), fictional-data ribbon, one `h1`, one lead
line, optional aside (the page's one way back). On a team's pages the
**team status line** sits under the header and above the body. Max content
1152px.

| State | Treatment |
|---|---|
| D | Eggwhite page, `h1` in Transducer 48, lead 22 muted |
| H/F | n/a (not interactive); links inside follow link rules |
| L | Title and ribbon render at once; body shows the page's own skeleton |
| E | n/a |
| X | Body replaced by a notice (6.20); title stays |
| Dis | n/a |

**Team status line (`TeamStatusBand`), added 2026-10-06 (issue #321).**
Ann's revisions of 2026-10-02: "Each team page has a line at the top that is
always visible: team number, which event, results used or not, way of asking
chosen or not, refresh done or not." Her checklist adds "round one or round
two", and that after a reload "the status line still shows where the team
is".

- **Where:** the four team pages (event picker, matching, results, asking
  for more), in the shell's `status` slot, so it is in the same place on each.
  Not on the opening screen, which comes before a team exists, and not on the
  instructor page, which is not a team's page and lists every team itself.
  It is at the top of the page; it is not pinned while the page scrolls.
- **What:** a surface card (`ce-card`), body size (never smaller than the
  list text), a wrapping `dl`. First "You are Team 3" in semibold. Then, as
  "label: **value**" pairs: each round with its event ("Round 1 · Northline
  Analytics: Behind the Business") and whether its results are used; "Way of
  asking"; "Refresh"; "Data file". Both rounds are always listed, so the
  line reads the same on every page; the round a page is about is marked in
  words, "(this page)". Under the pairs, in meta size, the link "Not your
  team? Pick again" to the opening screen.
- **Source:** three reads the team already has (its workspace, its events,
  its asking state). Nothing is kept in the browser and the team number is
  never read from `localStorage`, so a reload or a second tab shows the same
  line. A page asks for it again after one of its own changes lands (a run,
  a choice, a refresh); the previous line stays until the new one arrives.
- **Words** are written in the browser (`teamStatusWording.ts`); the
  refresh's are never a server sentence (6.19).

| State | Treatment |
|---|---|
| D | the pairs, values in semibold ink, labels muted |
| H/F | n/a for the line; the link follows link rules |
| L | "Reading your team's status…" in muted ink, same card |
| E | n/a: a team always has a number; a file with no rounds lists none |
| X | refused (no team entered, access gone): **nothing** is drawn, because the page below shows that sentence and the way back. Unreachable: "Your team's status could not be read. Reload the page to read it again." A later read that fails keeps the line and adds "This line could not be read again just now, so it may be out of date." |
| Dis | n/a |

It is a named region ("Your team's status"), not a live region: its first
appearance is part of the page loading. One `sr-only` polite line inside it
says the new line when it changes (§8.6).

### 6.2 Fictional-data ribbon

A slim full-width ribbon above the title: `Info` icon in `--ce-gold-ink`,
sentence in `--ce-type-meta`, background `--ce-gold-tint`, radius card, no
border. Text: the bold prefix **"Fictional data —"** (owner ruling
2026-09-26, replacing "Synthetic / demo data —" on exercise screens), then the
existing constant "All student profiles are fictional, shaped by overall
survey percentages." This replaces the loud amber banner on exercise screens
only, as a new `tone="quiet"` variant of `SyntheticDataBanner` with a `label`
prop; the CBA banner is unchanged and the component is not copied.

States: D is always visible and never dismissible. H, F, L, E, X and Dis are
n/a: the ribbon is not interactive and renders before any data loads.

### 6.3 Button

| Variant | D | H | F | L (pending) | Dis |
|---|---|---|---|---|---|
| Primary | `--ce-primary` fill, white label, radius control, 56px tall desktop / 48px on 390 | fill darkens 8%, `ce-lift` | focus ring | label changes to the in-progress verb ("Opening your team's work…"), 16px spinner leading, `aria-disabled` | 45% opacity, `not-allowed` cursor, reason in helper text via `aria-describedby` |
| Secondary | white fill, 2px `--ce-line-strong` outline, ink label | outline to `--ce-primary`, fill `--ce-primary-tint` | ring | as primary | as primary |
| Quiet | text-only, primary colour, underline on hover | underline 2px | ring | inline spinner | 45% opacity |
| Destructive confirm | `--ce-danger` fill, white label; only inside an inline confirm | darken 8% | ring | "Clearing…" | n/a |

One primary per region. E/X: n/a for buttons; errors appear in the region's notice.

### 6.4 Team tile (radio)

Numbered place card, 112×112 desktop, 96×96 on 390, Transducer 44 numeral.

| State | Treatment |
|---|---|
| D | white card, `elev-1`, numeral ink |
| H | `ce-lift`, numeral primary |
| F | ring around the tile (focus-within) |
| Selected | `--ce-primary` fill, white numeral, small gold corner notch |
| L | six skeleton tiles |
| E | n/a (numbers are a scope constant) |
| X | tiles stay; notice below with the server sentence |
| Dis | while submitting, all tiles 60% opacity |

### 6.5 Event round card

A wide card: round seal (circle with 1 or 2, from `round-journey.svg` geometry),
event name in Proxima Sera 32, the event's description when the data file has
one, "Topics:" and "Aimed at:" lines, trailing `ChevronRight`. Past events
render as a quiet list below, not cards.

**Event description (#318, Ann 2026-10-02).** The data file's
`event_description` text, printed as it arrives, at body size (`ce-type-body`,
the size of the ranked list's names; her checklist asks for "no smaller than
the list text"), `--ce-ink`, `ce-measure`. It sits under the event name on the
round card, at the top of the matching page above the sliders (§7.4), and
under the event name in the instructor's unlock row (§6.24). An event with no
description shows nothing: no placeholder, no gap. No description is written
in the frontend. On the card the link is named by the seal and the event name
(`aria-labelledby`) and described by the rest (`aria-describedby`), so the
link's name stays short.

| State | Treatment |
|---|---|
| D | white, `elev-1` |
| H | `ce-lift`, chevron slides 4px |
| F | ring |
| L | two card skeletons and four line skeletons |
| E | notice "This data file has no exercise events in it yet. The instructor can upload a file that does." |
| X | notice with the server sentence |
| Dis | n/a (a round card is a link) |

### 6.6 Weight slider (see [prompt](../../archive/design/class-exercise/prompts/components/weight-slider.md))

Label (Ann's words, from `factor_labels`), track, thumb, and a paired 88px
numeric field showing the value ("3"). Whole numbers 0–10, step 1 on the
slider (Dr. Wang's defaults are 3 / 3 / 2 / 2, ruling 2026-10-06, switched
2026-10-09; OQ-CE-34); the field keeps the strict-decimal rule and the server
refuses a fraction or a number above 10. A setting saved before the switch
keeps its fractions (shown as "0.25").
Commit on pointer-up, on Enter, or on field blur; never per drag tick.

| State | Treatment |
|---|---|
| D | track 6px `--ce-surface-sunk` with 2px `--ce-line-strong` outline; filled part `--ce-primary`; thumb 28px white disc with 2px primary ring |
| H | thumb grows to 32px, `elev-2` |
| F | ring on thumb; value readout bolds |
| Dragging | thumb 32px, value bubble above thumb |
| L (committed, list rebuilding) | slider stays live; tiny spinner beside the label; queued edits allowed |
| E | n/a (four factors always present) |
| X | field outline `--ce-danger`, message under field from the component ("Type a number for this weight.") or the server's refusal sentence |
| Dis | 45% opacity; never disabled during a refetch |

**Total weight (owner ruling 2026-09-28).** Under the four sliders, above the
"The list is rebuilt…" note, the card shows "Total weight: 10" (the sum of
the four numbers as shown, a whole number, tabular numerals, updated live while
dragging or typing) and one sentence: "What matters is how the weights
compare: a factor set to 6 counts twice as much as one set to 3." The
scorer divides each weight by the total, so the total is never forced to 10
and the 3 / 3 / 2 / 2 defaults stay. No percentage is shown anywhere
(ADR-0025 D8). When the total is 0 the card shows the server's own sentence,
"At least one number must be above 0.", as `role="status"`, and not again
while that refusal is already shown under a slider.

### 6.7 Ranked row with reason line (see [prompt](../../archive/design/class-exercise/prompts/components/ranked-row.md))

Desktop: table row. Columns: rank (Transducer 28, primary), name (Usual 600
20) with the reason line beneath (Proxima Sera 18, muted), major, year, marker
chip. No "Why" column: the reason sits under the name so the eye reads name
then why. 390: a stacked card per row with the same content order.

| State | Treatment |
|---|---|
| D | white row, 1px `--ce-line` divider |
| H | row wash `--ce-surface-sunk` (desktop only; not interactive) |
| F | n/a (rows are not focusable; the table is reachable by screen reader) |
| Joined | `ce-row-join` gold-tint wash |
| On both lists | persistent `--ce-gold-tint` wash, `Link2` chip "on both lists" in `--ce-gold` with `#17352A` text |
| Changed by the refresh | chips beside the name, one per `refresh_marks` value: `Sparkles` "New card" and "New: went to {first event}" on `--ce-primary-tint` with a `--ce-primary` rule; `MailX` "Stopped responding" on `--ce-surface-sunk` with a `--ce-line-strong` rule. Icon and words, never colour alone. A profile may carry several. None before the refresh |
| L | 8 skeleton rows with rank placeholders |
| E | "Nobody is on this list. Nobody in this data file can be ranked for this event with these weights." with `empty-state.svg` |
| X | list dims to 0.6 and a line under the header: "This is the list from before that change…" |
| Dis | n/a |

### 6.8 Marker chip ("how much we know")

Pill, `--ce-type-meta`, three variants, each icon + words, never colour alone:

| Marker | Icon | Fill / text |
|---|---|---|
| major only | `Circle` | `--ce-surface-sunk` / ink |
| major plus events attended | `CircleDot` | `--ce-avocado-tint` / ink |
| completed card | `IdCard` | `--ce-primary-tint` / `#003D24` |

Unknown values render their raw string in the neutral style. Not interactive.

The list download uses the same words: its fifth column is headed
"how much we know" and each cell holds one of the three phrases above, never
the API key. The file has six columns — rank, name, major, year, how much we
know, reason — and no others.

### 6.9 Composition table ("Who is on the list")

Three small tables (by major, by year, by how much we know), each with columns
"On this list" and "In the whole data file". Paired horizontal count bars are
**not** used (they read like a share). Plain tabular numerals, right-aligned.

| State | Treatment |
|---|---|
| D | white card |
| L | skeleton table |
| E | a group with 0 on the list shows `0` in ink, not muted |
| X | notice with the server sentence |
| H, F, Dis | n/a (read-only table) |

### 6.10 Coverage notice

One line with `Users` icon, `--ce-gold-tint` background: "Nobody on this list
is a Senior or an Accounting major." Hidden when nothing is missing.

### 6.11 Saved-setting card (see [prompt](../../archive/design/class-exercise/prompts/components/saved-setting-card.md))

Index-card style, three slots (the count is `max_settings` from the server).
Filled card: name (Proxima Sera 24), four weight rows (label + value in tabular
numerals, no bars), actions "Open this list" (secondary), "Compare" (checkbox
toggle), "Delete" (quiet, inline confirm). Empty slot: dashed 2px
`--ce-line-strong` outline, `empty-state.svg`, "Slot 2 of 3 is free. Save the
weights on screen to fill it."

| State | Treatment |
|---|---|
| D | white, `elev-1` |
| H | `ce-lift` |
| F | ring on each action |
| Selected for compare | 3px primary outline and a "Comparing" chip |
| L | `ce-card-save` on create; "Saving…" on the save button |
| E | all slots empty; the compare row reads "Save two settings to see them side by side." |
| X | notice above the row with the server sentence; the typed name stays in the field |
| Dis | once two cards are ticked, the third "Compare" toggle disables with the line "Two are chosen. Untick one to swap." |

**After a press (amended 2026-10-06, issue #321).** One notice (6.20) sits
under the save form and above the cards, beside the buttons it is about, and
says what the last press did: done tone for "Saved “Setting A” for Northline.
You have 2 of 3 slots left.", "Deleted “Setting A”. …", "Opened “Setting
A”. …", "Showing “A” and “B” side by side, below." and "Closed the
side-by-side view."; calm tone, with the server's own sentence, for a press
that was refused (state X above now means this notice, no longer one at the
top of the page). It stays until the next press in the panel replaces it; it
never times out. The slot counts come from the server's answer to the press.
"Opened “Setting A”. The list above is built from it." is a claim about the
list on screen, so it alone follows the list (amended 2026-10-06, PR #346
review): it appears once that setting's list has landed, not at the press;
if the read is refused or cannot be reached (the setting was deleted in
another tab) the notice is that sentence instead, calm tone, and not a second
live region, since the page's notice above the list already announces it;
and it is taken down when the team moves a weight or presses "Go back to
this list's weights".
Beside "The list" heading, "List updated." takes the place of "Rebuilding the
list…" once a list the team asked for has landed, and stays until the next
change.

### 6.12 Compare view (see [prompt](../../archive/design/class-exercise/prompts/components/compare-view.md))

Two ranked lists as tables stacked one above the other, each in its own
scroll box (768 and up; owner ruling 2026-09-27: two five-column tables with
major, year and marker do not fit side by side), or a segmented control A | B
(below 768),
summary sentence "12 names are on both lists, highlighted in each.", overlap
rows gold-washed with an "on both lists" chip, close action. On 390 each list
shows 10 rows and "Showing 10 of 30. Show all 30" (from Fable's Room
mock-up). Reference: [`room/compare-1280.png`](../../archive/design/class-exercise/assets/mockups/room/compare-1280.png),
[`room/compare-390.png`](../../archive/design/class-exercise/assets/mockups/room/compare-390.png).

### 6.13 Final-setting picker

Radio cards of the team's saved settings (not a `<select>`), each showing the
setting name and its four weights. Helper line: "Your team's invited list is
built from the setting you choose. Choose one to run results." Run button
disabled until chosen, with that line as its description.

### 6.14 Results lock panel

**Amended 2026-10-06 (issue #328).** This section used to say that teams
have no read of the lock, so the lock showed only after a refused press, the
panel had no action, and the run button vanished after the run. That was
deliberate, and it is reversed here on purpose: Ann's checklist of 2026-10-02
(section 5) asks for a results button that is grey **before** it is pressed,
that asks before the one run, and that stays on screen, grey, afterwards. The
team's events read now carries `results_open` and `results_run` for each
round, so the state is known on load.
The same two fields feed the team status line (6.1, issue #321): each round
reads "Results used", "Results not used yet (open now)" or "Results not
used yet (not open yet)", with run winning over open as below. The line is a
second reader of that read, not a second source: it shows what the server
says and decides nothing.

| State | Read | Treatment |
|---|---|---|
| Not open | `results_open` false, `results_run` false | `invitation-envelope.svg`, `Lock` chip "Results are closed", the sentence "Results for {event} are not open yet. Ask your instructor.", and a secondary "Check again" (a read of the lock, never the run). The final-setting picker stays, so a team can choose while it waits. Primary button, grey: "Results not open yet.", described by that sentence |
| Open, not run | `results_open` true, `results_run` false | final-setting picker, primary "Run results for this event" (grey until a setting is chosen, described by the picker's line). **First press asks, on the button itself:** "Send this list? You get one results run for {event}", with the `ce-confirm-window` underline; a second press inside 5 s sends the run; Escape, the window lapsing, or choosing another setting puts it back. A held Enter or Space never confirms |
| Already run | `results_run` true, or stored results on screen | primary button, grey: "Results already run for this event.", described by the line "A team runs results once per event."; the stored results render under it |

Rules that go with the table:

- **Run wins over open.** Results closed again after a team ran (issue #326)
  read as "already run", with the results still on screen.
- **Grey is `aria-disabled`, never the `disabled` attribute** (6.3), so the
  button stays focusable and its reason stays reachable.
- **Grey is what is shown, not what is allowed.** The server refuses a second
  run whatever the screen believes. A tab that was open before the run, or
  before results were closed, still has a live button; its press is answered
  with the server's sentence, and the screen then reads again and lands on the
  right state. That covers a second press, a reload, and a second tab.
- If the events read cannot say (it failed, or does not list the event), the
  button is live and the run route answers, as before this amendment.
- **Every press here says what it did** (issue #321). After the run the line
  under the grey button gives the time from the run itself: "Run at 10:42 AM.
  A team runs results once per event." "Check again" that finds results
  still closed says so under itself, "Checked at 10:43:07 AM. Results are
  still not open.", instead of leaving the screen unchanged. Only a read that
  landed says that: when the read could not be reached the line is the
  could-not-be-reached sentence instead, because nothing is then known about
  the lock (amended 2026-10-06, PR #346 review). The time is the browser's
  clock, to the second, so a second press in the same minute changes the line
  and is announced again; "Run at" is the server's time and stays to the
  minute.

### 6.15 Results reveal and seat figures (see [prompt](../../archive/design/class-exercise/prompts/components/results-reveal.md))

Seating chart (grid of `event_seats` squares, 10 per row → 6 rows for 60;
any other count fills rows of 10 and leaves the last row short), a small
"Front of the room" bar above row 1, legend, and the three-sentence summary
set as the screen's headline in Proxima Sera 40/48 (the Ledger's headline
idea), numerals in `--ce-primary`. Under it a **ruled figures band**, not
cards: three columns separated by 1px `--ce-line-strong` rules, each a
`--ce-type-display` numeral over a label: "Seats in the room 60", "Already
coming 8", "Still open 46". The "added" figure is the server's
`team.attended_count` (the server stores `seats_empty = 60 - 8 - attended`);
the client never subtracts. The seating chart is
`aria-hidden`; the sentences and the band are the accessible content.

### 6.16 Results chart

Recharts bar chart restyled to section 3.3 through a new `variant="exercise"` on `ExerciseResultsChart` (a variant, not a copy); panels in order: "Your team's
list", "If you emailed everyone", and in round two "Your team, round one".
Table fallback stays, visually as a quiet data table under a disclosure
"Show these counts as a table" (open by default on 390).

### 6.17 People chips

Invited, Signed up, Attended as three lists of name chips (`--ce-surface-sunk`,
radius pill). Heading shows the count. "Nobody." when empty.

### 6.18 Asking choice card (see [prompt](../../archive/design/class-exercise/prompts/components/asking-choice-cards.md))

Three full-width radio cards in a `radiogroup`. Label in Proxima Sera 24 (the
wording from `askingChoices.ts`), one supporting line, no percentages.

Each card carries a button "Choose this way". **Inline confirm (owner ruling
2026-09-26):** the first press turns that same button into "Confirm: A small
reward?" (the choice label without its final full stop) in `--ce-primary`
fill for about 5 seconds, with a thin countdown underline shrinking under
the label. A second press within the window commits; letting it lapse, or
pressing Escape, or choosing another card, reverts the button to "Choose this
way". No pop-up, no modal, no second button. Screen readers hear "Press again
to confirm A small reward. Your team picks once." via `aria-live="polite"`.
Reduced motion: no underline animation; the label change and a static
"5 seconds" helper carry it. Moving focus away (blur) does **not** disarm:
only the lapse, Escape, or another card reverts it, so a stray Tab does not
cost the class its moment. A held Enter or Space (key repeat) never counts as
the confirming press.

**After the choice (amended 2026-10-06, issue #321).** Under the cards, in
ink: "You chose: A small reward." followed, muted, by "A team picks once, so
these are now fixed." It is read from the server's own word, so it is still
there after a reload, and the status line (6.1) shows the same choice.

### 6.19 Refresh summary and counts

**Amended 2026-10-06 (Ann's review of 2026-10-02, checklist section 6).** The
refresh says that it happened, when, and what it changed. Three parts, in
this order under the button, all read from the asking response so a reload, a
second browser and a team the instructor refreshed show the same thing:

1. **Summary** (`RefreshSummary.tsx`): a done-tone notice (6.20) with one
   line of plain sentences (on Asking the notice is not `role="status"`: it
   mounts already filled, so an always-present `sr-only` `aria-live="polite"`
   line beside it, `exercise-refresh-announce`, carries the same sentences and
   is what a screen reader hears, once): "Refresh done at 10:42 AM. 9 people who came to
   Northline now count as having gone to a similar event. 12 of the 22 invited
   people with no card completed one. 0 people stopped responding." The time is
   the browser's local clock (`en-US`, "10:42 AM").
2. **Before and after**, inside the same notice: "How much we know, all 300
   profiles, before and after", then one line per group, most on file first:
   "Completed card: 70 → 82". A screen reader hears "70 before, 82 after".
   Every profile in the data file is counted, not only the ones on a list.
3. **Figures band**, as 6.15: "Cards filled in", "Stopped opening messages",
   "Picked up the first event's topics". The third figure counts *people*, not
   topics (`topics_added` is `len(gainers)` in `results_repository.py`), so
   the label names people. Values count up once.

The shut button reads "Already refreshed at 10:42 AM" (6.3 Dis). A second
press from another tab is answered with the same words, not with a refusal.

**The button asks first (amended 2026-10-06, issue #321).** The refresh
happens once per team and cannot be undone, like the run (6.14) and the
choice (6.18), so "Ask them now" uses the same `ce-confirm-window`: the
first press sends nothing and the button reads "Ask them now? Your team can
ask only once", with the line "Press again to ask. Your team cannot ask a
second time, and it cannot be undone." under it; a second press inside 5 s
asks; Escape or the window lapsing puts it back; a held Enter or Space never
confirms. One component (`AskOnceButton`) on both screens that offer it.

**The server sends facts; the screen writes these sentences**
(`refreshWording.ts`). The server's own sentences say "asking", never
"refresh" (`test_exercise_results_asking_wording.py`), and it has no way to
know the room's time zone. Ann's review words the outcome as "Refresh done"
and "Already refreshed", so those words are used for it; the button that
starts it keeps "Ask them now". Counts only: no percentage is composed.

### 6.20 Notice

| Tone | Treatment |
|---|---|
| Calm (refusal) | `--ce-surface` card, `elev-1`, `Info` icon in primary, server sentence at body size, optional one action |
| Problem (transport) | `--ce-surface` card, 2px `--ce-danger` outline, `TriangleAlert`, sentence, "Try again" |
| Done (success) | `--ce-avocado-tint` wash, `CircleCheck` in primary, `role="status"` |

No left border stripe. `ce-notice-in` on appear.

### 6.21 Loading skeletons (see [prompt](../../archive/design/class-exercise/prompts/components/empty-and-loading-states.md))

Content-shaped blocks in `--ce-surface-sunk`, `ce-skeleton`. Each skeleton has
a visually hidden `role="status"` "Loading the list…" so the stated-loading
rule in the parent contract still holds.

### 6.22 Profile card mock-up

A phone-sized card (360px wide) centred on an eggwhite desk, with a diagonal
"Mock-up only" stamp chip in the top-right corner (not rotated text; a chip).
Contents: "Two quick questions", major confirm, two questions with dashed
answer lines, inert buttons labelled as inert.

### 6.23 Points counter

Ticket-stub card: profile name (Proxima Sera 24), total in
`--ce-type-display`, "points" in lead size, two rows "From attending events"
and "From completing a card", card-state chip. "not available" in words when a
figure is null. **Deferred (orchestrator call, 2026-09-26):** no page and no
mock-ups this round; it waits until an endpoint returns `ProfilePoints`. The
spec stays so the later build starts from it.

### 6.24 Instructor components

Passcode field (with show/hide toggle), dropzone for `.xlsx`, dataset row,
invite-limit stepper, team row (6), unlock row, refresh-every-team panel. See
[instructor prompt](../../archive/design/class-exercise/prompts/pages/11-instructor.md) and
[unlock panel prompt](../../archive/design/class-exercise/prompts/components/instructor-unlock-panel.md).

| State | Dropzone | Unlock row | Team row |
|---|---|---|---|
| D | dashed 2px outline, `FileSpreadsheet`, "Drop Ann's workbook here, or choose a file" | event name + `Lock` chip "Results closed" + "Open results" secondary; a closed-again event adds "Closed at 10:50 AM."; the event's description under them when the data file has one (§6.5) | team seal, file label, counts, actions |
| H | outline primary, wash `--ce-primary-tint` | lift | lift |
| F | ring | ring on button | ring on each action |
| L | "Uploading and checking the file…" with determinate stages: Reading → Checking columns → Saved | "Opening…" / "Closing…" | "Clearing…" |
| E | "No data file has been uploaded yet." | "{file} has no events for the teams to run." | "No team has entered a number yet." |
| X | server sentence under the zone, file name kept; the report of an earlier upload is removed (#325) | server sentence inline | server sentence inline |
| Dis | while uploading | — (see the note below: an open row is no longer a dead end) | during a pending action |

**Unlock row, amended 2026-10-06 (issue #326).** Ann's revisions of
2026-10-02: "Opening or closing results for an event shows the time it was
done, and results can be closed again." So an open row is `LockOpen` chip
"Results open", the line "Opened at 10:42 AM.", and a secondary "Close
results". Closing asks first, inline, in the same sunk well as opening:
"Close results for {event}? …" with "Close results now" and "Keep them open".
The chip words follow her checklist exactly ("Results closed" / "Results
open"); the team-side lock panel keeps its own chip (6.14). After either
change lands, focus goes to the event's name and never to the opposite action,
so a repeated Enter cannot undo what was just done.

**Team row, opened — amended 2026-10-06 (issue #319).** "Open this team's
work" used to list the names of a team's saved settings and one line of counts
per run. Ann's revisions of 2026-10-02: the instructor leads the discussion
from this page and needs the whole team. The opened view sits in the same sunk
well, in this order:

1. One status line: the way of asking the team chose and whether it has
   asked, with the time ("Way of asking: A small reward. Asked at 10:42 AM.").
2. **Saved settings.** Per setting: its name; "Round 1 · {event}"; **the four
   numbers** as a two-column `dl` under Ann's words for the four factors
   (never a factor key, never a score); and **"Its list (30)"** — the names
   that setting builds now, an ordered list, each name followed by major,
   year and the "how much we know" marker in words.
3. **Results.** Per run: "Round 1 · {event}"; the setting it was built from,
   and a sentence when that setting has been deleted since; the four numbers
   the run used; the D8 seats sentence; then "Invited (30)", "Signed up (14)"
   and "Attended (11)" as three lists of names.

Each list is a native `<details>`, open by default, so thirty names can be
folded away on a small screen without a pop-up. A run's names are the run's own
record (issue #271): they do not change when the team edits or deletes the
setting. A run stored before names were kept shows its counts and the line
"Names were not kept for this run."; nothing is filled in, and names without a
rank are a plain list, not a numbered one. Marking is in words, never colour
alone (§8).

**Refresh-every-team panel (amended 2026-10-06, Ann's review of
2026-10-02).** Title "Refresh every team at once". The button's label says
what it does: "Refresh every team that has chosen how to ask" (it was "Ask for
every team"). After it runs, a done-tone notice (6.20) carries a headline,
"Refreshed 2 teams. Skipped 3 teams.", and one line per team in the Teams
panel's order, the team's name in bold:

- refreshed: the summary that team reads on its own screen (6.19), then the
  completed-card count before and after;
- skipped: the reason in words, from the server's `reason_code`
  (`no_asking_choice`, `no_round_one_run`, `already_refreshed`). An unknown
  code reads "Skipped." and invents no reason.

Only teams that exist are listed; a team nobody has entered as is absent, as
it is from the Teams panel. When a team number appears more than once in the
report (teams in more than one data file), every name carries its file's
label: "Team 3 (October file):". A label is not unique, so a repeated number,
not a second label, is what turns this on. The
request is one transaction: refused, it changes no team and shows the server's
sentence instead of a report.

**It asks first (amended 2026-10-06, issue #321).** Ann's revisions of
2026-10-02: buttons that change work for everyone "ask “Are you sure?” first
and say what will change". The button opens the question in the panel, in
the same sunk well as opening results: "Refresh every team that has chosen
how to ask? Each of those teams is refreshed once, and that cannot be undone
or done again. Teams that have not chosen, and teams already refreshed, are
not changed." with primary "Refresh them now" and quiet "Not yet". Only
"Refresh them now" sends the request. "Not yet" and Escape put the button
back and send nothing. Focus moves to "Refresh them now" when the question
appears and back to the panel's button when it goes. It is the two-button
form, not the five-second window: the sentence is too long to read against a
timer. Every run asks again.

**The press that asks cannot also answer (amended 2026-10-06, PR #346
review).** Because focus moves onto the confirming button, a held Enter would
repeat on it and a double-click would land on it, sending the request with
the question unread. On "Refresh them now", "Open results now" and "Close
results now" a repeated Enter or Space (key repeat) is ignored however long
the key is held, and any press inside the 300 ms guard after the question
opens is ignored (the same guard length as `ce-confirm-window`, section 5).
Clearing a team and moving every team do not move focus onto their "yes", so
a held key never reaches it. The refresh-every-team well is a `group` named
by its question (`aria-labelledby`), so the scope sentence is read with the
button focus lands on, once: it is not also the button's description and not
a live region.

**The three class-wide confirms, side by side (issue #321).** Clear a team:
"This clears team 3's saved settings and result runs. No other team is
touched." Move every team: "This moves every team to this file and clears
the work of every team it moves." Refresh every team: the question above.
All three are inline, name their scope, and have a way out that sends
nothing.

**After a press (issue #321).** Clearing a team shows a done-tone notice at
the top of the Teams panel, "Team 3 cleared at 10:42:07 AM. It is back at
the start. No other team was changed.", which stays until the next clear (the
time is the browser's clock when the answer landed; the server sends none).
Setting the list limit shows "Limit set to 25." in the Data files panel's
done slot. The Teams panel says "Teams last read at 10:43:07 AM." under its
lead line, so "Check the teams again" visibly did something even when no
team changed. These two lines and the results screen's "Checked at …" are
the only times read off the browser's clock, and the only ones shown to the
second (amended 2026-10-06, PR #346 review): to the minute, a second press
in the same minute rewrote the line with the same words. Times the server
recorded ("Run at", "Refreshed at", "Opened at", "Closed at") stay to the
minute.

## 7. Page layouts

Routes and file names are the current ones. Wireframes are schematic.

### 7.1 Opening screen (`/exercise`, top zone)

- **1280:** two columns 7/5. Left: `h1` "Who should we invite?" (the
  question from Fable's "The Room"), lead "Your team is promoting a campus
  career event with 60 seats. Choose whom to invite, see what happened, then
  try again.", then the license line in a
  quiet sunk card. Right: `lecture-hall.svg` at 160px in `--ce-primary`.
  Below: the team entry zone.
- **390:** single column; illustration hidden; license card full width.

### 7.2 Team entry (`/exercise`, lower zone)

- **1280:** `h2` "Which team are you?", six tiles in one row, primary button
  "Open this team's work" right-aligned under the tiles. "This browser is
  already in team 4, working in Ann's file, 25 September." line with
  `team-badge.svg` at 32px.
- **390:** tiles in a 3×2 grid; button full width, sticky to the bottom safe
  area once a tile is chosen.

### 7.3 Event picker (`/exercise/events`)

- **1280:** `h1` "Choose an event"; two round cards stacked full width; below,
  `h2` "Past events, for attendance history" and a two-column quiet list of ten.
- **390:** cards stack; past events single column, collapsed behind a
  disclosure "Show the 10 past events".

### 7.4 Matching (`/exercise/events/:eventKey`)

```
1280
┌───────────────────────────────────────────────────────────────┐
│ ribbon                                                        │
│ Northline Analytics (h1)            Team 4 · Choose another → │
│ lead                                                          │
│ The event's description, from the data file (§6.5)            │
├──────────────────┬────────────────────────────────────────────┤
│ How much each    │ The list (h2)     Rebuilding…  Download ⤓  │
│ thing counts     │ Cut at 30 names…                           │
│ [slider] 0.40    │ 1  Maya Okafor              Accounting …   │
│ [slider] 0.25    │    What counted: same major; said they …   │
│ [slider] 0.25    │ 2  …                                       │
│ [slider] 0.10    │ … 30 rows                                  │
│ (sticky, 360px)  │                                            │
├──────────────────┴────────────────────────────────────────────┤
│ Who is on the list (3 tables in a row)                        │
│ Your team's saved settings (3 cards in a row)                 │
│ Compare (when open)                                           │
│ Next: Go to results for this event (primary)                  │
└───────────────────────────────────────────────────────────────┘
```

- **390:** weights card first (four sliders stacked); when it scrolls out, a
  sticky compact bar shows the four values and "Edit weights" (scrolls back).
  Ranked rows become cards. Composition tables become three disclosures.
  Saved settings stack.

### 7.5 Saved settings and compare (same route, lower zone)

- **1280:** three setting cards in a row, a "Name these weights" field and
  "Save these weights" button above them. Compare opens below as two
  stacked tables, each in its own scroll box (owner ruling 2026-09-27).
- **390:** cards stack; compare shows a segmented control "Setting A | Setting B"
  with the summary sentence pinned above.

### 7.6 Profile card mock-up (`/exercise/profile-card`)

- **1280:** centred 360px phone-sized card on the desk, with a left caption
  column (max 360px) explaining "This is what a profile would be asked."
- **390:** card fills the width; caption above.

### 7.7 Points counter (component frame; not routed)

Deferred this round (see 6.23).

- **1280:** a row of three ticket stubs for three fictional profiles.
- **390:** stubs stack.

### 7.8 Results, round one (`/exercise/events/:eventKey/results`)

```
1280
┌───────────────────────────────────────────────────────────────┐
│ Results (h1)                              ← Back to your list │
│ lead                                                          │
├───────────────────────────────────┬───────────────────────────┤
│ Seating chart 10×6                │ 8 were already coming.    │
│ ▪▪▪▪▪▪▪▪■■                          │ Your invitations added 6. │
│ ■■■■□□□□□□                          │ 46 seats are still open.  │
│ □□□□□□□□□□ …                        │ 60 │ 8 │ 46  (figures band)│
├───────────────────────────────────┴───────────────────────────┤
│ What happened for Northline Analytics (chart, 3 series × 2)   │
│ The people on your team's list (chips)                        │
│ Ask the people your team invited → Asking for more            │
└───────────────────────────────────────────────────────────────┘
```

Before a run, while results are not open: lock panel (6.14) in the
seating-chart position. After a run: the grey "Results already run for this
event." button sits above the seating chart.
- **390:** seating chart full width (10 per row, 26px seats), sentences below,
  the figures band stays three columns at 40px numerals, chart switches to horizontal
  bars.

### 7.9 Asking for more (`/exercise/asking`)

- **1280:** `h1` "Asking for more"; `partly-known-card.svg` (96px) right of
  the "How will your team ask?" `h2` (the shell's header has no slot beside
  the lead);
  three choice cards in a row; below, "Ask the people your team invited" with
  the primary button and, after it runs, the summary notice with the
  before-and-after lines, then three count cards (6.19).
- **Before round one has results** the three cards are not drawn. One line
  stands in their place: "Your team picks a way of asking after it has its
  results for {first event}." (Ann, 2026-10-02: "The choice appears only after
  the team has its round-one results.")
- **390:** cards stack; button full width.

### 7.10 Round-two comparison (results for the second event)

- **1280:** `round-journey.svg` strip at the top ("Round 1 → Round 2"), the
  seat chart for round two, then the chart with three series groups, then a
  quiet line: "In round one your team's list left 46 seats empty." Round two
  headline: "8 were already coming. Your invitations added 11. 41 seats are
  still open."
- **390:** as 7.8 with the extra panel as a third chart group.

### 7.11 Instructor (`/exercise/instructor`)

- **Signed out, 1280:** a centred 480px card: `KeyRound`, "Passcode" field,
  "Open the instructor page".
- **Signed in, 1280:** two columns 8/4. Left: "Open results for an event"
  (unlock panel) first, then "Teams" (six rows), then "Refresh every team at
  once". Right: "Data files" (dropzone, dataset rows, invite limit) and
  "Sign out of this browser".
- **The right column is not sticky (as built, #250).** At 1280 it is
  1615–2411px tall (dropzone, upload report, one or more data files, an open
  "Move every team" confirm), taller than any laptop window. A sticky column
  taller than the window hides its own bottom, "Move every team to this file"
  and "Sign out of this browser", until the left column ends; a scroll box
  inside the column clipped the same controls. It scrolls with the page.
- **390:** single column in the order unlock, teams, refresh-every-team, data
  files, sign out.

## 8. Accessibility (WCAG 2.2 AA)

1. **Contrast:** every text pair in section 3 was checked (ratios listed).
   Gold and avocado never carry text or a sole signal on light surfaces.
2. **Non-text contrast:** control outlines, slider track, open-seat outlines
   and bar strokes use `--ce-line-strong` or darker (≥3:1).
3. **Not colour alone:** markers have icons and words; overlap has a chip and
   text; seats have fill, mark and outline plus a legend and sentence; chart
   series have hatch/solid/open plus direct labels.
4. **Keyboard:** team tiles are a radio group (arrow keys); sliders are Radix
   `Slider` (arrows ±0.05, Page ±0.25, Home/End); choice cards are a radio group
   with an explicit "Choose this way" confirm; every action reachable by Tab
   in visual order.
5. **Focus:** 3px primary ring, 3px offset; never removed. Route change moves
   focus to the `h1`.
6. **Live regions:** "Rebuilding the list…" and the seat sentences are
   `aria-live="polite"`, announced once. Refusals use `role="status"`, not
   `alert`; field errors use `role="alert"`. What a press did (issue #321) is
   a done-tone notice with `role="status"`, or a polite line that was already
   on the page. The team status line is announced only when it changes.
7. **Tables:** ranked list and composition stay real `<table>`s at ≥768px; the
   390 card view is an `<ol>` with the same content order.
8. **Reduced motion:** every motion in section 5 has a stated fallback.
9. **Targets:** at least 44×44px; slider thumb hit area 44px even when drawn 28px.
10. **Zoom:** layouts hold at 200% zoom on 1280 (reflows to the 768 layout).

## 9. Content voice

- **Data wording:** describe the data only as "fictional profiles shaped by
  overall survey percentages". Do not say where the percentages came from or
  who answered. Every generated mock-up must follow this.
- **Names in mock-ups:** fictional, diverse, plausible for a Southern
  California business school. Use the set in
  [`prompts/README.md`](../../archive/design/class-exercise/prompts/README.md#7-shared-fictional-data) so screens agree.
- **Sentence case** everywhere; direct verbs on buttons ("Save these
  weights", "Run results for this event", "Open results").
- **Seat sentences:** exactly the pattern "{existing} were already coming.
  Your invitations added {added}. {open} seats are still open." with singular
  forms ("1 was already coming", "1 seat is still open").
- **Refusals:** the server's sentence, verbatim, never prefixed with "Error".
- **Never:** "score", "match %", "confidence", "AI-powered", "optimize",
  "insights", "demo", "winner", "you beat".
- **Tone:** a helpful teaching assistant: plain, warm, brief. No exclamation marks.

## 10. Do and don't

| Do | Don't |
|---|---|
| Use CPP Eggwhite as the page and white as the card | Add a new hue, a gradient background, or gradient text |
| Keep one primary button per region | Put two green buttons side by side |
| Put the reason line directly under the name | Hide the reason in a tooltip or truncate it |
| Show weights as numbers the team chose | Draw a bar, ring or percentage for a person |
| Let the seats fill once, then rest | Loop the reveal, add confetti, or say "great job" |
| Use gold for exactly one highlight per screen | Use gold for text on white or for buttons |
| Render refusals as calm cards | Use red for "results are locked" |
| Keep the license line on the opening screen in every state | Move it to a footer or hide it on phones |
| Use spot art only in empty, locked and first-visit states | Put an icon or illustration beside a page title |
| Keep cards one level deep | Nest a card inside a card |
| Use a sticky compact weights bar on 390 | Let the list scroll the sliders out of reach with no way back |
| Name the fictional profiles plainly | Describe the data's origin beyond "fictional profiles shaped by overall survey percentages" |

## 11. Open items for the owner

All six items were ruled on 2026-09-26. The heading keeps its name so
existing links still land here.

| # | Item | Ruling | Ruled by | Where it now lives |
|---|---|---|---|---|
| 1 | Ribbon prefix | **"Fictional data —"** on exercise screens | Owner | 6.2; prompts README preambles |
| 2 | Weights input | **Slider 0–10, step 1, plus a number box** (was 0–1, step 0.05; changed 2026-10-09) | Owner | 6.6; `prompts/components/weight-slider.md` |
| 3 | Asking-for-more confirm | **Inline confirm:** the button becomes "Confirm: <choice>?" for about 5 s; no pop-up | Owner | 6.18, motion `ce-confirm-window`; `prompts/components/asking-choice-cards.md`, `prompts/pages/09-asking-for-more.md` |
| 4 | Points counter | **Deferred.** No page or mock-ups until an endpoint exists | Orchestrator | 6.23, 7.7; `prompts/pages/07-points-counter.md` marked deferred |
| 5 | Shared components | **New variants, not copies** (`SyntheticDataBanner` `tone="quiet"` + `label`; a chart `variant="exercise"`) | Orchestrator | 6.2, 6.16 |
| 6 | New wording | **Use as drafted**; listed below for Ann to see | Orchestrator | 11.1 |

### 11.1 New wording for Ann to see

Every string this refresh adds. Server sentences, factor labels, choice
labels and the license line are unchanged and not listed.

| Where | New text |
|---|---|
| Event picker, each round card (#334; pending Ann's sign-off) | "Round one" / "Round two" |
| Event picker, the round-two card (#334; pending Ann's sign-off) | "Opens after round one (Session 2)" |
| Ribbon prefix (every screen) | "Fictional data —" |
| Team status line, every team page (2026-10-06, #321; Ann's checklist §3 wording for the team) | "You are Team 3" |
| Team status line, a round (#321; the instructor page's "Round 1 · …" form) | "Round 1 · Northline Analytics: Behind the Business:" / on that event's own pages "Round 1 · Northline Analytics: Behind the Business (this page):" |
| Team status line, whether a round's results are used (#321) | "Results used" / "Results not used yet (open now)" / "Results not used yet (not open yet)" |
| Team status line, way of asking (#321; the choice labels, without the full stop) | "Way of asking: A small reward" / "Way of asking: Not chosen yet" |
| Team status line, refresh (#321; written in the browser) | "Refresh: Done at 10:42 AM" / "Refresh: Done" (no time known) / "Refresh: Not done yet" |
| Team status line, data file (#321; the file's own label) | "Data file: October file" |
| Team status line, wrong team (#321) | "Not your team? Pick again" |
| Team status line, loading and failing (#321) | "Reading your team's status…" / "Your team's status could not be read. Reload the page to read it again." / "This line could not be read again just now, so it may be out of date." |
| Team status line, the region's name for a screen reader (#321) | "Your team's status" |
| Opening `h1` | "Who should we invite?" |
| Opening lead | "Your team is promoting a campus career event with 60 seats. Choose whom to invite, see what happened, then try again." |
| Event picker, 390 past-events disclosure | "Show the {n} past events" / "Show the 1 past event" (same label when expanded) |
| Matching, slider note | "The list is rebuilt when you let go of a slider or press Enter." |
| Matching, after a rebuilt list lands (2026-10-06, #321; Ann's checklist §4 wording) | "List updated." |
| Matching, weight total | "Total weight: 10" |
| Matching, weight total meaning | "What matters is how the weights compare: a factor set to 6 counts twice as much as one set to 3." |
| Matching, 390 sticky bar | "Weights 3 · 3 · 2 · 2 · Total 10" and "Edit weights" |
| Matching, a weight that is a fraction or above 10 (2026-10-09) | "A weight is a whole number from 0 to 10." |
| Matching, a typed weight that is not a number (2026-10-09; was "Use digits and one decimal point, like 0.5.") | "\"abc\" is not a plain number. Use a whole number from 0 to 10, like 3." |
| Matching, downloaded list (CSV), fifth column | Header "how much we know" (was "marker"); cells "major only" / "major plus events attended" / "completed card" (were the API keys). No new wording: the same label and phrases as the marker chip (§6.8). |
| Saved settings, field label | "Name these weights" (was "Call these weights") |
| Saved settings, empty slot | "Slot 3 of 3 is free. Save the weights on screen to fill it." |
| Saved settings, compare limit | "Two are chosen. Untick one to swap." |
| Saved settings, delete confirm | "Delete Balanced? It cannot be brought back." / "Delete it" / "Keep it" |
| Saved settings, save in progress | "Saving…" |
| Saved settings, after a save (2026-10-06, #321; Ann's example, with the event's own name and the server's counts) | "Saved “Setting A” for Northline Analytics: Behind the Business. You have 2 of 3 slots left." |
| Saved settings, after a delete (#321) | "Deleted “Setting A”. You have 3 of 3 slots left." |
| Saved settings, after "Open this list", once that list has landed (#321; taken down when the team asks for another list) | "Opened “Setting A”. The list above is built from it." |
| Saved settings, after "Show them side by side" and after closing it (#321) | "Showing “Setting A” and “Setting B” side by side, below." / "Closed the side-by-side view." |
| Saved settings, card chosen for compare | "Comparing" |
| Compare, 390 | "Showing 10 of 30. Show all 30" |
| Results, room | "The room", "Front of the room", legend "Already coming", "Your invitations", "Still open" |
| Results, seat headline | "8 were already coming. Your invitations added 6. 46 seats are still open." (pattern from the brief) |
| Results, figures band | "Seats in the room", "Already coming", "Still open" |
| Results, lock chips | "Results are closed" / "Results are open" |
| Results, button before results are open (2026-10-06, #328; Ann's checklist wording) | "Results not open yet." |
| Results, why it is not open (#328; Ann's example sentence, also the server's answer to a run) | "Results for Northline Analytics: Behind the Business are not open yet. Ask your instructor." |
| Results, re-read the lock (#328) | "Check again" |
| Results, question before the one run (#328; Ann's checklist wording, event name substituted) | "Send this list? You get one results run for Northline Analytics: Behind the Business" |
| Results, spoken and shown hint while the question is up (#328) | "Press again to send this list. Your team cannot run this event a second time." |
| Results, button after the run (#328; Ann's checklist wording) | "Results already run for this event." |
| Results, why it cannot be run again (#328; 6.14's line, now on screen) | "A team runs results once per event." |
| Results, when the run was made (2026-10-06, #321; in front of the line above) | "Run at 10:42 AM." |
| Results, after "Check again" finds results still closed (#321; browser's clock, to the second) | "Checked at 10:43:07 AM. Results are still not open." (no time known: "Checked. Results are still not open.") |
| Results, after "Check again" when the read could not be made (2026-10-06, PR #346 review; the could-not-be-reached sentence, under the button) | "The exercise could not be reached. Check the connection and try again." |
| Results, table disclosure | "Show these counts as a table" |
| Round two | "In round one your team's list left 46 seats empty." |
| Asking, supporting lines | "Tell them a card helps us suggest events worth their evening." / "Offer something small for a completed card." / "Make the card a condition of hearing about events." |
| Asking, buttons | "Choose this way" → "Confirm: A small reward?" |
| Asking, spoken hint | "Press again to confirm A small reward. Your team picks once." |
| Asking, after the choice, on screen (2026-10-06, #321; Ann's checklist §6 wording; the second sentence is the existing one) | "You chose: A small reward. A team picks once, so these are now fixed." |
| Asking, before round one has results (in place of the three cards) | "Your team picks a way of asking after it has its results for Northline." (falls back to "the first event") |
| Asking and Results, refresh summary (2026-10-06, from Ann's checklist) | "Refresh done at 10:42 AM. 9 people who came to Northline now count as having gone to a similar event. 12 of the 22 invited people with no card completed one. 0 people stopped responding." |
| Refresh summary, singular forms | "1 person who came to Northline now counts as having gone to a similar event." / "1 of the 1 invited person with no card completed one." / "1 person stopped responding." |
| Refresh summary, nobody invited was without a card | "Everyone your team invited already had a card." |
| Refresh summary, time not known | "Refresh done." |
| Asking, before-and-after heading | "How much we know, all 300 profiles, before and after" |
| Asking, before-and-after lines | "Completed card: 70 → 82" / "Major plus events attended: 64 → 58" / "Major only: 166 → 160" (spoken: "70 before, 82 after") |
| Asking and Results, shut refresh button (was "Your team has already asked") | "Already refreshed at 10:42 AM" (without a time: "Already refreshed") |
| Asking and Results, the refresh button asking first (2026-10-06, #321) | "Ask them now? Your team can ask only once" |
| Asking and Results, shown and spoken hint while it asks (#321) | "Press again to ask. Your team cannot ask a second time, and it cannot be undone." |
| Ranked list, marks on a changed profile | "New card" / "New: went to Northline" (falls back to "New: went to the first event") / "Stopped responding" |
| Profile-card page `h1` | "What a profile would be asked" |
| Profile card, stamp chip | "Mock-up only" |
| Profile-card caption | "Major and year are already on file, and past events are recorded when someone attends. So the card asks only two things, and asks the person to confirm their major." |
| Instructor, passcode helper | "The passcode is shared by the course team. It is not your university login." |
| Instructor, unlock confirm | "Open results for Harbor Consumer Brands? Every team can then run results once for this event." / "Open results now" / "Not yet" |
| Instructor, dropzone | "Drop Ann's workbook here, or choose a file" |
| Instructor, passcode show/hide toggle (accessible name; `aria-pressed` carries the state) | "Show what is typed" |
| Instructor, unlock confirm in progress | "Opening…" |
| Instructor, lock chips (2026-10-06, #326; Ann's checklist wording) | "Results closed" / "Results open" |
| Instructor, when results were opened or closed (#326) | "Opened at 10:42 AM." / "Closed at 10:50 AM." |
| Instructor, close button (#326) | "Close results" |
| Instructor, close confirm (#326) | "Close results for Northline Analytics? Teams that have not run results yet cannot run them until you open results again. Results already run stay on each team's screen." / "Close results now" / "Keep them open" |
| Instructor, close confirm in progress (#326) | "Closing…" |
| Instructor, a close the database refused (#326; server sentence, shown at the top of the page) | "The results for that event could not be closed." |
| Instructor, an open or a close asked for a past event (#326 review; the server's existing sentence for a team's run on a past event, reachable only by a hand-written request — the panel lists the two rounds) | "Results are only run for the two rounds of the exercise." |
| Instructor, a team's way of asking and whether it has asked (2026-10-06, #319; the page's existing words, with the time added) | "Way of asking: A small reward. Asked at 10:42 AM." / "Way of asking: A small reward. Has not asked yet." / "Has not picked a way of asking. Has not asked yet." / "Way of asking: A small reward. Has already asked." (when the time cannot be read) |
| Instructor, a team's opened work, headings (#319) | "Saved settings" / "Results" |
| Instructor, a team's opened work, which event (#319) | "Round 1 · Northline Analytics: Behind the Business" |
| Instructor, a team's opened work, list headings with their counts (#319) | "Its list (30)" / "Invited (30)" / "Signed up (14)" / "Attended (11)" |
| Instructor, one name on a list (#319; major, year and marker as on file) | "Brandon Soto — Accounting, Senior, completed card" |
| Instructor, a team's opened work, nothing there (#319) | "No saved settings yet." / "No results run yet." / "Nobody on this list." / "Nobody." |
| Instructor, which setting a run was built from (#319) | "Built from the setting “Wide net”." / "Built without a saved setting." |
| Instructor, a run whose setting was deleted afterwards (#319, #271) | "Built from the setting “Wide net”. The team has deleted that setting since; this run is unchanged." |
| Instructor, a run's counts (#319; D8 wording, kept) | "Invited 30, signed up 14, attended 11. 46 seats are still open." |
| Instructor, a run stored before names were kept (#319, #271) | "Names were not kept for this run." |
| Instructor, after a team is cleared (2026-10-06, #321; Ann's checklist §2 "Team X cleared.", with the time and the scope) | "Team 3 cleared at 10:42:07 AM. It is back at the start. No other team was changed." (no time known: "Team 3 cleared. …") |
| Instructor, when the Teams panel was last read (#321; browser's clock, to the second) | "Teams last read at 10:43:07 AM." |
| Instructor, after the list limit is set (#321; Ann's checklist §2 wording) | "Limit set to 25." |
| Instructor, upload in progress | "Uploading and checking the file…" |
| Instructor, upload done (#325; composed on the page from the server's file name and counts) | "SmartMatch_Student_Body_300.xlsx — 300 profiles, 12 events loaded." |
| Instructor, upload refused (#325; the server's sentence, now sent without backticks) | "The Events sheet is missing the column seats." |
| Instructor, upload refused, a description too long (#325; server sentence) | "Row 12 of the Events sheet has more than 2000 characters in the column event_description; please shorten it and upload again." |
| Instructor, every-team panel title (was "Ask for every team at once") | "Refresh every team at once" |
| Instructor, every-team button (was "Ask for every team") | "Refresh every team that has chosen how to ask" |
| Instructor, every-team explainer | "This refreshes, in one go, every team that has chosen a way of asking and has not been refreshed yet. Teams that are not ready are skipped, and the list below says why. If it cannot be done, no team is changed." |
| Instructor, every-team in progress (was "Asking for every team…") | "Refreshing every team…" |
| Instructor, every-team confirm (2026-10-06, #321) | "Refresh every team that has chosen how to ask? Each of those teams is refreshed once, and that cannot be undone or done again. Teams that have not chosen, and teams already refreshed, are not changed." / "Refresh them now" / "Not yet" |
| Instructor, every-team report headline | "Refreshed 2 teams. Skipped 3 teams." (singular: "1 team") |
| Instructor, every-team report, nobody has entered | "No team has entered a number yet, so there was nothing to refresh." |
| Instructor, every-team report, a refreshed team | "Team 2: Refreshed at 10:42 AM. 9 people who came to Northline now count as having gone to a similar event. 12 of the 22 invited people with no card completed one. 0 people stopped responding. Completed card: 70 → 82." |
| Instructor, every-team report, skipped teams | "Team 4: Skipped: it has not chosen a way of asking." / "Team 5: Skipped: it has not run results for its first event." / "Team 1: Skipped: it was already refreshed at 10:31 AM." (no time known: "…it was already refreshed.") / unknown reason: "Skipped." |
| Instructor, every-team report, teams in two data files | "Team 3 (October file): …" |
