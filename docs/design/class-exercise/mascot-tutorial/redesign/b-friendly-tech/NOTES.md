# Direction B: Friendly Tech

**Open:** `http://127.0.0.1:8765/redesign/b-friendly-tech/` (the server on port 8765 serves `docs/design/class-exercise/mascot-tutorial`).
**Status:** mockup for owner review. It is not app code. Nothing in `apps/` changed.
**Files:** `index.html` (markup), `styles.css` (tokens and layout), `app.js` (behaviour, no libraries), `screenshots/`.
**Mascot art:** loaded from `../../mockup/assets/*.webp`. Nothing is copied.

## Concept

This direction is a calm, modern product in the Linear or Arc register, with a Duolingo shape: one task card at a time, and one blue button that says what happens next. The canvas is a cool near-white, the ink is slate, and one electric blue does every job an action does. A soft pink, taken from the mascot's coat, does exactly one other job: it marks what the class should look at ("on both lists", "nobody on this list is…", gentle errors). A slim rail on the left shows the six steps, so the page never has to explain where you are. Bree lives in a small "Tour" pill in the corner. She says one short line when a screen opens, then goes quiet. For the tour she grows into a card, and the target on the page gets a blue spotlight ring. Everything else (tables, past events, who came) sits behind a disclosure.

## Palette

Colour strategy: restrained. Neutrals, one accent, one highlight tint. No Cal Poly green or gold.

### Light (default; a lit classroom and a projector)

| Token | Hex | Use |
|---|---|---|
| `--canvas` | `#F6F7FB` | Page |
| `--surface` | `#FFFFFF` | Cards, action bar, companion |
| `--sunk` | `#EEF1F6` | Wells, tiles, disabled button, skeleton |
| `--ink` | `#131A2A` | Text |
| `--ink-2` | `#505A6E` | Secondary text, reason lines |
| `--line` | `#E3E7EF` | Decorative dividers only |
| `--line-strong` | `#7E889C` | Control outlines, open seats, dashed slots |
| `--accent` | `#2D5BFF` | Primary button, slider fill, "your invitations" seats, focus ring |
| `--accent-press` | `#1E47E6` | Primary hover and press |
| `--accent-tint` | `#E8EEFF` | Selected pick, "completed card" chip |
| `--accent-ink` | `#1B3FCC` | Blue text: ranks, links, figures |
| `--pink` | `#FF7AA2` | Decorative only: tour ring pulse, selected-tile dot |
| `--pink-tint` | `#FFE8EF` | Highlight wash: both lists, coverage line, gentle error, text selection |
| `--pink-ink` | `#A3214F` | Pink-coded text ("On both lists", overlap count) |
| `--seat-taken` | `#5B6478` | "Already coming" seats |
| `--danger` | `#C0262D` | Reserved for transport errors (not used on these screens) |

### Dark (a dimmed room, or an OS set to dark)

`--canvas #0D111A`, `--surface #151B27`, `--sunk #1D2433`, `--ink #EEF1F7`, `--ink-2 #A9B2C3`, `--line #2A3242`, `--line-strong #6B7488`, `--accent #7B98FF`, `--on-accent #0D111A`, `--accent-tint #1E2A4F`, `--accent-ink #B9C8FF`, `--pink-tint #3A2030`, `--pink-ink #FFB3C9`, `--seat-taken #A9B2C3`.

### Contrast (WCAG 2.x, computed)

| Pair | Light | Dark | Needs |
|---|---|---|---|
| ink on canvas | 16.23:1 | 16.69:1 | 4.5 |
| ink on surface | 17.37:1 | 15.24:1 | 4.5 |
| ink-2 on surface | 6.93:1 | 8.08:1 | 4.5 |
| ink-2 on canvas | 6.48:1 | 8.85:1 | 4.5 |
| ink-2 on sunk (disabled button text) | 6.12:1 | 7.28:1 | 4.5 |
| on-accent on accent (primary button) | 5.18:1 | 6.99:1 | 4.5 |
| accent on canvas (links, numerals) | 4.84:1 | 6.99:1 | 4.5 |
| accent-ink on surface | 7.99:1 | 10.48:1 | 4.5 |
| accent-ink on accent-tint (chip) | 6.89:1 | 8.52:1 | 4.5 |
| ink on accent-tint | 14.98:1 | — | 4.5 |
| pink-ink on pink-tint | 6.25:1 | 8.78:1 | 4.5 |
| pink-ink on surface | 7.27:1 | 10.30:1 | 4.5 |
| ink on pink-tint | 14.92:1 | 12.99:1 | 4.5 |
| seat-taken on surface | 5.93:1 | 8.08:1 | 3 (non-text) |
| line-strong on canvas / surface / sunk | 3.33 / 3.57 / 3.15:1 | 4.03:1 on canvas | 3 (non-text) |
| pink on surface | 2.45:1 | — | decorative only, never text or a sole signal |
| review bar muted text on bar | 8.87:1 | — | 4.5 |

## Type

- **Sora** (600, 700) for headings, ranks and big numerals. It is a geometric sans with round, friendly counters that stays crisp at 40px. It carries the tech-friendly voice without looking like a code editor.
- **Geist** (400, 500, 600) for everything a hand operates or an eye reads: body, labels, tables and buttons. It has tabular numerals (used for weights, counts and ranks) and holds up at 16px on a projector.
- **Sizes:** h1 40px (30px on mobile), tracking −0.03em. Section h2 20px. Body 18px (16px on mobile). No data text is smaller than 13px, and all reading text is at least 15px.
- **Fonts cost** two Google Fonts families and 5 weights. Production would self-host them.

## Layout principles

1. **One task card per view, one primary action.** Every screen has a single blue button. On the list, compare and results screens it sits in a sticky action bar at the bottom, like Duolingo's "Check" button. Everything else is secondary or quiet.
2. **The rail replaces explanations.** Six steps on the left (a segmented bar at 390) show where you are and what is done. Headings can then stay short.
3. **Tuck, don't delete.** Past events, the three "who is on the list" tables, "see who came" and rows 7 to 30 of the list all sit behind a disclosure. Every required fact is still one click away.
4. **Pink means "look here", and only that.** It marks overlap, the coverage gap and gentle errors. Blue means action and "your team".
5. **Single column, 760 to 940px wide,** centred in the space beside the rail. Results is the only screen that splits into two columns: the seat chart beside "email everyone".
6. **Calm states.** A locked result is a waiting mascot, not a red alert. An error is a surprised face with one sentence on how to fix it.

### Clutter: visible text blocks per screen, before and after

**Method:** in each screen's `<main>`, count every visible element that has its own text, with closed disclosures and screen-reader-only text excluded. Measured with the same script on both mockups at 1440×900. "Before" is `mockup/index.html`.

| Screen | Before: blocks / words | After: blocks / words | Change |
|---|---|---|---|
| Team entry | 14 / 87 | 12 / 71 | −14% blocks |
| Event picker | 15 / 102 | 9 / 55 | −40% |
| Weights + list | 91 / 396 (12 rows) | 50 / 252 (6 rows, plus the "who is on the list" summary and coverage line, which the old mockup lacked) | −45% |
| Compare two settings | 101 / 429 (the list screen with compare on) | 67 / 194 (two top-10 lists side by side) | −34% blocks, −55% words |
| Results, locked | 7 / 51 | 6 / 39 | −14% |
| Results, open | 14 / 73 (seats only) | 12 / 72 (final-setting picker) · 25 / 83 once run | +11 blocks after the run: this is the required "email everyone" table (Invited, Signed up, Attended × 2), which the old mockup did not have |
| Asking for more | not in the old mockup | 12 / 77 before choosing · 16 / 89 when done | new screen |

Per ranked row: 6 blocks before (rank, name, reason, major, marker, year) → 5 after (rank, name, "major · year", marker, reason).

The companion's one-line hint sits outside `<main>` and is not counted. It auto-hides after 6 s, and the menu can turn it off.

## Pose-to-moment map

Every pose and every face has a job.

| Asset | Moment | Where |
|---|---|---|
| `pose1-guide` | **Welcome** | Perched on the team card on the opening screen. Tour steps 1 ("Hi, I'm Bree") and 3 ("Open your work") |
| `pose2-chill` | **Idle / waiting** | Results locked: "Waiting for the instructor" |
| `pose3-explore` | **Empty state, and "look at this"** | Compare with only one saved setting ("Save one more setting to compare"). The empty list when all weights are 0. Tour steps 2, 4 and 6 (pointing at things) |
| `pose4-worker` | **Loading / working** | "Rebuilding the list…" skeleton. "Running your team's list…" before results. Tour step 5 (set the weights) |
| `pose5-celebrate` | **You're done** | "Round one is done." card after asking for more. Tour step 7 ("You're ready") |
| `face1-happy` | Companion at rest | The "Tour" pill by default. Team and event hints |
| `face2-surprised` | **Gentle error** | All weights at 0 (inline notice). Save with an empty name. Open with no team picked |
| `face3-curious` | **Thinking** | While the list rebuilds. Hints on list, compare and asking ("Who is missing from every list?") |
| `face4-laugh` | **Success** | "Results are open". "Saved as …". "That's round one done" |
| `face5-calm` | Calm / quiet | Results-locked hint. "Tour closed…" after Skip. Hints turned off |

## Tour and companion

- **Steps:** 7, with the baseline mockup's copy and order.
- **Card:** grows out of the Tour pill. It has Next, Back, Skip, and "Don't show this again".
- **Keyboard:** ← → move between steps and Esc skips. Focus moves to the step title. An `aria-live` line reads "Step n of 7. Title. Text."
- **Dialog:** the card is `role="dialog"` with `aria-modal="false"`, so the spotlit control stays usable.
- **Seen state:** `localStorage['smartmatch.exercise.tour.v1']`, the same key as the plan. Every read and write is guarded.
- **Dockable:** the pill's menu has "Replay the tour", "Move to the left/right" and "Turn off hints". The side and hint choice are remembered per browser.
- **Reduced motion:** the OS setting or Review → "Simulate reduced motion". Every animation drops to a 150 ms fade. No bob, no spring, no seat pop, no shimmer, no countdown bar ("Press again within 5 seconds" is added to the text instead).
- **Asking inline confirm:** follows DESIGN.md §6.18. The first press shows "Confirm: A small reward?" with a 5 s underline. Escape, a lapse or another card reverts it. A held key never confirms. The live region says "Press again to confirm … Your team picks once."

## Motion

- **Easing:** springy but restrained. Pops use `cubic-bezier(.34, 1.36, .64, 1)`. Entrances use an exponential ease-out.
- **The one authored moment:** the results reveal. The 8 taken seats fill, then the team's 6 pop in, then the three sentences rise one by one.
- **Everything else is feedback:**
  - list rows FLIP to their new rank when a slider is released;
  - a name new to the list flashes pink;
  - the tour card springs out of the pill;
  - the compare overlap rows wash in.
- **Performance:** transform and opacity only. The one exception is the spotlight box, as in the baseline plan. There are no libraries and no canvas.

## Review deep links

`?screen=team|events|list|compare|results|asking` · `&team=4` · `&results=locked|open|ran` · `&compare=one` · `&weights=zero` · `&loading=1` · `&ask=small_reward&asked=1` · `&theme=dark` · `&rm=1` · `&step=1..7` or `&step=none` · `&hint=off`

The **Review** menu in the top bar toggles the same states.

## Deviations and detector notes

- **Brief pinned, no concept roll.** The impeccable skill asks for PRODUCT.md, a concept roll and a finish reviewer. The dispatch brief pinned this direction and limited writes to this folder, so the build is code-led from the brief. No PRODUCT.md, DESIGN.md or `.impeccable/` files were written.
- **`impeccable detect` findings I kept, on purpose:**
  - spring easing (the brief asks for "springy");
  - the skeleton shimmer (loading only, and off under reduced motion);
  - Geist flagged as "overused" (chosen as a workhorse UI face);
  - the spotlight animating left, top, width and height (a single fixed element, as in PLAN.md §4).
- **Fixed:** the coloured glow in dark mode, and two width/height transitions.
- **Asset artefact:** `pose3-explore.webp` carries a stray tail fragment from the sheet in its bottom-left corner. It is masked with a small `clip-path` until a clean export exists.

## 3 things to refine next

1. **Clean 2× mascot exports.** Get 2× exports of all five poses from the artist, with transparent edges and no stray fragments. The current crops are 262–286px and soft on HiDPI. The explore pose needs the mask above. A true "pointing" pose would also make tour steps 2, 4 and 6 read better than the magnifier does.
2. **Mobile sticky weights.** On 390 the four sliders scroll away from the list. Add the compact sticky bar from DESIGN.md §7.4 (the four values plus "Edit weights") so cause and effect stay on one screen.
3. **Round two and the projector.** Design the round-two results, with the team's round-one column beside "email everyone". Then test the whole flow projected at 1280×720 from the back row: the 15px secondary text and the pink tint may need one step more contrast on a washed-out projector.
