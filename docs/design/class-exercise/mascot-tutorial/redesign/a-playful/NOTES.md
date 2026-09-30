# Direction A · Playful Learning

**Open:** `http://127.0.0.1:8765/redesign/a-playful/` (serve `docs/design/class-exercise/mascot-tutorial` on port 8765).
**Status:** mockup for owner review. It is not app code. Nothing in `apps/` changed.
**Files:** `index.html`, `styles.css`, `app.js` (112 kB raw, 28 kB gzipped), and `screenshots/`. The mascot art is referenced from `../../mockup/assets/`, not copied.

## Concept

It works like a lesson path. Each screen asks one question. The progress bar at the top shows where the team is, and one big button at the bottom does the next thing. Bree speaks in a speech bubble on every screen and changes pose to match the moment: waving hello, sleeping on a cloud while results are closed, typing while the list rebuilds, a surprised face when every weight is 0. When a step is done, the bottom bar turns lilac, her happy face pops up, a few sparks fly, and **Continue** turns coral. Anything a team needs only sometimes sits behind a "more" control: a row's major and year, the past events, the download, the "who is on the list" counts, and the profile-card preview.

## Palette

Light is the default, because the screens are projected in a lit room. Dark follows the OS, or use **Review → Light / dark**. There is no Cal Poly green or gold anywhere in the palette. The green in the art is Bree's polo shirt.

| Token | Light | Dark | Use |
|---|---|---|---|
| `--page` / `--surface` | `#FFFFFF` | `#14112A` / `#1D1938` | Page, cards |
| `--wash` / `--wash-2` | `#F5F3FF` / `#ECE9FB` | `#221D42` / `#2A2450` | Wells, tracks, value pills |
| `--line` / `--line-strong` | `#E6E3F5` / `#8A86A6` | `#3A3462` / `#7F79AB` | Borders, pressed edges / 3:1 control outlines |
| `--ink` / `--ink-2` | `#1E1A3D` / `#57536F` | `#F4F2FF` / `#BDB8DE` | Text / secondary text |
| `--primary` (violet) | `#5B3DF5`, edge `#3F24C4` | `#A594FF`, edge `#6B55E0` | Primary buttons, slider fill, selected state |
| `--primary-tint` / `--primary-ink` | `#ECE8FF` / `#3A22B8` | `#2E2766` / `#D4CBFF` | Selected fills, "completed card" marker, success band |
| `--coral` (warm accent) | `#FF7A59`, edge `#E0532F` | `#FF8F70`, edge `#D9603F` | The Continue button, "on both lists", seats still empty |
| `--coral-tint` / `--coral-ink` | `#FFEDE6` / `#B03A16` | `#3D2224` / `#FFB9A5` | Fictional-data pill, shared-name rows |
| `--sky` (secondary) | `#2BA8F0` | `#5CC2FF` | "Who is on the list" button and panel |
| `--sky-tint` / `--sky-ink` | `#E2F3FF` / `#07598A` | `#13324A` / `#9ED9FF` | "Major plus events attended" marker |
| `--sun` | `#FFC53D` | same | Tour spotlight ring and sparks only |
| `--blush` | `#FFE3DE` | `#3D2433` | Circle behind Bree's face art, taken from her cheeks |
| `--danger-tint` / `--danger-ink` | `#FFECEC` / `#A3142B` | `#3F1A22` / `#FFB3B8` | The gentle error |

WCAG contrast for the text pairs (computed, sRGB relative luminance):

| Pair | Light | Dark |
|---|---|---|
| ink on page | 16.53 | 16.61 |
| ink on wash | 15.07 | 15.21 (on surface) |
| ink-2 on page / on wash | 7.31 / 6.67 | 8.87 (on surface) |
| on-primary on primary (button text) | 6.12 | 7.24 |
| primary-ink on primary-tint | 8.36 | 8.63 |
| on-coral on coral (Continue) | 6.88 | 7.92 |
| coral-ink on page / on coral-tint | 6.06 / 5.34 | 8.77 (on tint) |
| sky-ink on sky-tint | 6.59 | 8.73 |
| danger-ink on danger-tint | 6.86 | 8.97 |
| ink on sun | 10.47 | — |
| line-strong on page (non-text, needs 3:1) | 3.48 | 4.19 (on surface) |
| review bar text / muted on bar | 14.11 / 8.17 | — |

Every pair passes AA for body text. Most pass AAA.

## Type

- **Fredoka 500/600** (Google Fonts) is the display face, for headings, team numerals, the results headline and the results table figures. Its round terminals match the rounded buttons and the chibi art.
- **Nunito 500–800** (Google Fonts) is for body text and UI. It is a rounded sans that stays readable at 15 px, and buttons use weight 800.
- Numbers use `font-variant-numeric: tabular-nums`.
- Sizes: `h1` 40 px on desktop and 28 px on mobile. Bubble text is 20 px and 16 px. Body is 18 px and 16 px. Nothing that carries data is under 13 px.

## Layout principles

1. **One decision per screen.** There are 8 screens: Team, Event, Weights + list, Compare, Results closed, Results open, Ask, Done. Save and compare moved off the weights screen, so that screen asks one question: "How much does each thing count?"
2. **A progress path, not a score.** It has 6 steps with one label ("Step 3 of 6 · Weights"). Its `aria-valuetext` gives the step. The tour says outright that "It is not a score" (ADR-0025 D8).
3. **One primary action, always in the same place.** The fixed bottom bar holds the hint on the left and the big button on the right. On step completion it becomes the celebration band.
4. **Bree on every screen.** On narrow screens she sits left of the bubble. On wide screens she sits right, beside the heading, so the work area starts higher.
5. **Chunky and pressable.** Buttons, tiles and option cards have a 4–5 px bottom edge that collapses on `:active`. Radii are 16–22 px.
6. **Progressive disclosure.** Each list row shows the name, the reason and the marker. Major and year are behind the row's chevron. Download is behind the `⋯` menu. "Who is on the list" is behind a sky button, with tabs for how much we know, major and year. The past events and the profile-card preview are behind "Show…" links. "Aimed at" appears only for the event you picked.
7. **Parity kept.** The reason line, the "how much we know" marker, the 30-name cap, and the total line with its exact sentence all stay visible. So do the shared-name highlight, the lock, "email everyone", seats still empty, the three asking choices with the inline confirm, the fictional-data notice and the license line.

### Clutter: visible text blocks per screen

**Method.** A text block is a visible element with its own text, counted once. The count leaves out the review bar, the tour layer and screen-reader-only text. It covers the whole page at 1440×900 before any interaction. It was measured with the same script on the old mockup (`mockup/?step=none`) and on this one.

| Screen | Before | After | What changed |
|---|---|---|---|
| Team entry | 9 | **7** | The lead moved into Bree's bubble. The ribbon became a pill. The `h2` and helper merged into one question. |
| Event picker | 14 | **12** | "Aimed at" shows only for the event you picked. The past events went behind a disclosure. |
| Weights + list | 84 | **40** | Save and compare moved to their own screen. Major and year are behind the row chevron, and download is behind `⋯`. |
| Compare (old: matching with compare on) | 94 | **41** | Rows are compact. Reasons are behind the chevron. One key replaces the "On both lists" tag that was on every shared row. |
| Results, closed | 8 | 9 | Adds Bree's bubble. The duplicate "Results are closed" chip was removed. |
| Results, open | 15 | 25 | +14 table cells: this adds the required **"email everyone"** column and the **seats still empty** row, which the old mockup did not have. |
| Asking for more | — | 14 | New screen (the old mockup had none). |
| Done | — | 11 | New screen. |

The screens that carried the clutter went from **178 to 81 blocks** (Weights + list and Compare: 84+94 → 40+41). Results, open, grew because it now shows content the requirements ask for.

## Pose-to-moment map

Every asset has a job. A pose swap is a 150 ms fade under reduced motion.

| Asset | Moment |
|---|---|
| `pose1-guide` | **Welcome**: the team screen, and tour steps 1 and 3 |
| `pose2-chill` | **Idle / waiting**: results are closed ("I'll wait here with you"), and the "Tour closed" toast |
| `pose3-explore` | **Exploring and empty states**: the event picker, results open ("See who came"), the empty compare state, and tour steps 2 and 5 |
| `pose4-worker` | **Working / loading**: the weights screen, "Rebuilding the list…" (the idle bob stops and she types), and tour steps 4 and 6 |
| `pose5-celebrate` | **You're done**: the Done screen, and the tour's last step |
| `face1-happy` | **Success micro-moment**: the bottom band on every completed step, "Saved as…", and the download toast |
| `face2-surprised` | **Gentle error**: every weight at 0 (she replaces the worker pose, with a wiggle), and saving with no name |
| `face3-curious` | **Thinking**: the compare screen ("Who drops off when interests count more?") |
| `face4-laugh` | **Results open**: the toast when the instructor unlocks, and the Done screen bubble |
| `face5-calm` | **Calm decision**: the asking-for-more screen, and the Tour pill in the top bar |

## Tour

- It has 7 steps. They are anchored by `data-tour` (`teams`, `path`, `weights`, `list`, `next`), and 2 steps are centred.
- Controls:
  - **Next** and **Back**
  - **Skip tutorial**, which shows a toast with the chill pose
  - **Don't show this again**
  - ← and → to move between steps, and Esc to skip
- Accessibility:
  - The card is `role="dialog" aria-modal="false"`, so the spotlit control can still be used.
  - Focus moves to the step title on each step.
  - An `aria-live` region reads "Step n of 7. Title. Text."
  - The mascot is `aria-hidden`.
- Storage: seen-state uses the same key as the plan, `smartmatch.exercise.tour.v1`, and every read and write is wrapped in try/catch.
- Reduced motion:
  - Pose swaps become a 150 ms fade.
  - The spotlight jumps instead of sliding.
  - There are no sparks, no hop and no seat pop.
  - The tour listens to the OS setting, or use **Review → Simulate reduced motion**.
- Mobile: the tour card is a bottom sheet, with Bree tucked into its top-right corner.

## Review controls and deep links

- The review bar (dark, at the top) jumps between the 8 screens.
- **Review** opens a panel that can:
  - show a state: list loading, gentle error, or empty compare;
  - replay the tour, or forget "seen";
  - switch light and dark;
  - simulate reduced motion.
- Deep links:
  - `?screen=entry|events|weights|compare|locked|open|ask|done`
  - `&team=4&event=northline&ask=1`
  - `&state=loading|error|empty`
  - `&who=1`, which opens the "who is on the list" panel
  - `&yay=1`, which shows the celebration band
  - `&step=N|none`
  - `&tour=off`, `&theme=dark` and `&rm=1`

## Performance (weak classroom PCs)

- **Scripts.** There are no JS libraries and no CDN scripts, only `app.js` (plain, deferred). Fonts come from Google Fonts: 2 families, 6 weights.
- **Images.** Only `pose1-guide` is preloaded (13 kB). The other poses load lazily, one per screen, at about 12–15 kB each.
- **Motion.** Animations use `transform` and `opacity`. There are two exceptions: the progress fill width, and the spotlight box, which is one fixed element.
- **Idle animation.** The only idle loop is a 3.2 s bob on the one visible mascot.
- **Reliability.** A scripted click-through from Team to Done ran with 0 console errors and 0 warnings.

## Conflicts to flag

- **Violet primary.** The brief asks for a violet primary. The `design-taste` skill warns against "AI purple". The brief wins, but the violet is kept flat, with no glows and no gradients.
- **Bottom edges.** The pressed bottom edge is a hard offset shadow, which the craft floor bans outside neobrutalism. The brief asks for it, so it stays.
- **Celebrations.** DESIGN.md §4 and §10 say "no confetti". The sparks fire on **step completion** and on the **instructor unlock**, never on the team's result. The results headline itself stays calm. This is the owner's call, as with effect 4 in PLAN.md.
- **Copy.** The copy has no exclamation marks (DESIGN.md §9). It shows no percentages; the asking choices show no shares.

## 3 things to refine next

1. **The weight total is just below the fold at 1440×900.** It shows as soon as the page scrolls, because the weights card is sticky. Fix it by tightening the factor rows, or by moving the total into the card header.
2. **Round two is not designed yet.** It needs the third results column ("Your team, round one") and a profile-refresh screen between Ask and round two. The profile-card questions shown under "What would the card ask?" are placeholder wording for Ann.
3. **Art.** Export the poses at 2×, because the 176 px crops are soft on HiDPI and `pose3-explore` has a stray tail fragment at its left edge. Also ask the artist for a **pointing** pose, so the tour spotlight steps can point at their target.
