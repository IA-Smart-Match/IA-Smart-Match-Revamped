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

- [`prompts/README.md`](prompts/README.md): how to generate screens from this system.
- [`experiments.md`](experiments.md): directions explored and why this one won.
- [`assets/svg/`](assets/svg/): the spot art this system allows.
- [`assets/mockups/`](assets/mockups/): 8 reference PNGs from the Fable
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
- **Spot art:** the geometric SVGs in [`assets/svg/`](assets/svg/). They are
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
line, optional aside (team and event). Max content 1152px.

| State | Treatment |
|---|---|
| D | Eggwhite page, `h1` in Transducer 48, lead 22 muted |
| H/F | n/a (not interactive); links inside follow link rules |
| L | Title and ribbon render at once; body shows the page's own skeleton |
| E | n/a |
| X | Body replaced by a notice (6.20); title stays |
| Dis | n/a |

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
event name in Proxima Sera 32, "Topics:" and "Aimed at:" lines, trailing
`ChevronRight`. Past events render as a quiet list below, not cards.

| State | Treatment |
|---|---|
| D | white, `elev-1` |
| H | `ce-lift`, chevron slides 4px |
| F | ring |
| L | two card skeletons and four line skeletons |
| E | notice "This data file has no exercise events in it yet. The instructor can upload a file that does." |
| X | notice with the server sentence |
| Dis | n/a (a round card is a link) |

### 6.6 Weight slider (see [prompt](prompts/components/weight-slider.md))

Label (Ann's words, from `factor_labels`), track, thumb, and a paired 88px
numeric field showing the value to two decimals. Range 0–1, step 0.05 on the
slider; the field accepts any plain decimal and keeps the strict-decimal rule.
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

### 6.7 Ranked row with reason line (see [prompt](prompts/components/ranked-row.md))

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

### 6.11 Saved-setting card (see [prompt](prompts/components/saved-setting-card.md))

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

### 6.12 Compare view (see [prompt](prompts/components/compare-view.md))

Two ranked lists side by side (1280) or a segmented control A | B (390),
summary sentence "12 names are on both lists, highlighted in each.", overlap
rows gold-washed with an "on both lists" chip, close action. On 390 each list
shows 10 rows and "Showing 10 of 30. Show all 30" (from Fable's Room
mock-up). Reference: [`room/compare-1280.png`](assets/mockups/room/compare-1280.png),
[`room/compare-390.png`](assets/mockups/room/compare-390.png).

### 6.13 Final-setting picker

Radio cards of the team's saved settings (not a `<select>`), each showing the
setting name and its four weights. Helper line: "Your team's invited list is
built from the setting you choose. Choose one to run results." Run button
disabled until chosen, with that line as its description.

### 6.14 Results lock panel

| State | Treatment |
|---|---|
| Locked | `invitation-envelope.svg`, `Lock` chip "Results are closed", the server sentence, and "Check again" (secondary) |
| Unlocked, not run | `LockOpen` chip "Results are open", final-setting picker, primary "Run results for this event" |
| Already run | results render; the run button is gone and a line says "A team runs results once per event." |

### 6.15 Results reveal and seat figures (see [prompt](prompts/components/results-reveal.md))

Seating chart (grid of `event_seats` squares, 10 per row → 6 rows for 60;
any other count fills rows of 10 and leaves the last row short), a small
"Front of the room" bar above row 1, legend, and the three-sentence summary
set as the screen's headline in Proxima Sera 40/48 (the Ledger's headline
idea), numerals in `--ce-primary`. Under it a **ruled figures band**, not
cards: three columns separated by 1px `--ce-line-strong` rules, each a
`--ce-type-display` numeral over a label: "Seats in the room 60", "Already
coming 8", "Still open 46". The "added" figure is the server's
`team.signed_up_count`; the client never subtracts. The seating chart is
`aria-hidden`; the sentences and the band are the accessible content.

### 6.16 Results chart

Recharts bar chart restyled to section 3.3 through a new `variant="exercise"` on `ExerciseResultsChart` (a variant, not a copy); panels in order: "Your team's
list", "If you emailed everyone", and in round two "Your team, round one".
Table fallback stays, visually as a quiet data table under a disclosure
"Show these counts as a table" (open by default on 390).

### 6.17 People chips

Invited, Signed up, Attended as three lists of name chips (`--ce-surface-sunk`,
radius pill). Heading shows the count. "Nobody." when empty.

### 6.18 Asking choice card (see [prompt](prompts/components/asking-choice-cards.md))

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
"5 seconds" helper carry it.

### 6.19 Refresh counts

The same ruled figures band as 6.15: "Cards filled in", "Stopped opening
messages", "Topics added from the first event". Values count up once.

### 6.20 Notice

| Tone | Treatment |
|---|---|
| Calm (refusal) | `--ce-surface` card, `elev-1`, `Info` icon in primary, server sentence at body size, optional one action |
| Problem (transport) | `--ce-surface` card, 2px `--ce-danger` outline, `TriangleAlert`, sentence, "Try again" |
| Done (success) | `--ce-avocado-tint` wash, `CircleCheck` in primary, `role="status"` |

No left border stripe. `ce-notice-in` on appear.

### 6.21 Loading skeletons (see [prompt](prompts/components/empty-and-loading-states.md))

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
invite-limit stepper, team row (6), unlock row, ask-for-every-team panel. See
[instructor prompt](prompts/pages/11-instructor.md) and
[unlock panel prompt](prompts/components/instructor-unlock-panel.md).

| State | Dropzone | Unlock row | Team row |
|---|---|---|---|
| D | dashed 2px outline, `FileSpreadsheet`, "Drop Ann's workbook here, or choose a file" | event name + `Lock` chip + "Open results" secondary | team seal, file label, counts, actions |
| H | outline primary, wash `--ce-primary-tint` | lift | lift |
| F | ring | ring on button | ring on each action |
| L | "Uploading and checking the file…" with determinate stages: Reading → Checking columns → Saved | "Opening…" | "Clearing…" |
| E | "No data file has been uploaded yet." | "{file} has no events for the teams to run." | "No team has entered a number yet." |
| X | server sentence under the zone, file name kept | server sentence inline | server sentence inline |
| Dis | while uploading | once open: `LockOpen` chip "Results are open", no button | during a pending action |

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
  "Save these weights" button above them. Compare opens below as two columns.
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

Before a run: lock panel (6.14) in the seating-chart position.
- **390:** seating chart full width (10 per row, 26px seats), sentences below,
  the figures band stays three columns at 40px numerals, chart switches to horizontal
  bars.

### 7.9 Asking for more (`/exercise/asking`)

- **1280:** `h1` "Asking for more"; `partly-known-card.svg` right of the lead;
  three choice cards in a row; below, "Ask the people your team invited" with
  the primary button and, after it runs, three count cards.
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
  (unlock panel) first, then "Teams" (six rows), then "Ask for every team at
  once". Right, sticky: "Data files" (dropzone, dataset rows, invite limit) and
  "Sign out of this browser".
- **390:** single column in the order unlock, teams, ask-for-all, data files,
  sign out.

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
   `alert`; field errors use `role="alert"`.
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
  [`prompts/README.md`](prompts/README.md#7-shared-fictional-data) so screens agree.
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
| 2 | Weights input | **Slider 0–1, step 0.05, plus a number box** for exact values | Owner | 6.6; `prompts/components/weight-slider.md` |
| 3 | Asking-for-more confirm | **Inline confirm:** the button becomes "Confirm: <choice>?" for about 5 s; no pop-up | Owner | 6.18, motion `ce-confirm-window`; `prompts/components/asking-choice-cards.md`, `prompts/pages/09-asking-for-more.md` |
| 4 | Points counter | **Deferred.** No page or mock-ups until an endpoint exists | Orchestrator | 6.23, 7.7; `prompts/pages/07-points-counter.md` marked deferred |
| 5 | Shared components | **New variants, not copies** (`SyntheticDataBanner` `tone="quiet"` + `label`; a chart `variant="exercise"`) | Orchestrator | 6.2, 6.16 |
| 6 | New wording | **Use as drafted**; listed below for Ann to see | Orchestrator | 11.1 |

### 11.1 New wording for Ann to see

Every string this refresh adds. Server sentences, factor labels, choice
labels and the license line are unchanged and not listed.

| Where | New text |
|---|---|
| Ribbon prefix (every screen) | "Fictional data —" |
| Opening `h1` | "Who should we invite?" |
| Opening lead | "Your team is promoting a campus career event with 60 seats. Choose whom to invite, see what happened, then try again." |
| Matching, slider note | "The list is rebuilt when you let go of a slider or press Enter." |
| Matching, 390 sticky bar | "Weights 0.40 · 0.25 · 0.25 · 0.10" and "Edit weights" |
| Saved settings, field label | "Name these weights" (was "Call these weights") |
| Saved settings, empty slot | "Slot 3 of 3 is free. Save the weights on screen to fill it." |
| Saved settings, compare limit | "Two are chosen. Untick one to swap." |
| Saved settings, delete confirm | "Delete Balanced? It cannot be brought back." / "Delete it" / "Keep it" |
| Compare, 390 | "Showing 10 of 30. Show all 30" |
| Results, room | "The room", "Front of the room", legend "Already coming", "Your invitations", "Still open" |
| Results, seat headline | "8 were already coming. Your invitations added 6. 46 seats are still open." (pattern from the brief) |
| Results, figures band | "Seats in the room", "Already coming", "Still open" |
| Results, lock chips | "Results are closed" / "Results are open" |
| Results, table disclosure | "Show these counts as a table" |
| Round two | "In round one your team's list left 46 seats empty." |
| Asking, supporting lines | "Tell them a card helps us suggest events worth their evening." / "Offer something small for a completed card." / "Make the card a condition of hearing about events." |
| Asking, buttons | "Choose this way" → "Confirm: A small reward?" |
| Asking, spoken hint | "Press again to confirm A small reward. Your team picks once." |
| Profile-card page `h1` | "What a profile would be asked" |
| Profile-card caption | "Major and year are already on file, and past events are recorded when someone attends. So the card asks only two things, and asks the person to confirm their major." |
| Instructor, passcode helper | "The passcode is shared by the course team. It is not your university login." |
| Instructor, unlock confirm | "Open results for Harbor Consumer Brands? Every team can then run results once for this event." / "Open results now" / "Not yet" |
| Instructor, dropzone | "Drop Ann's workbook here, or choose a file" |
