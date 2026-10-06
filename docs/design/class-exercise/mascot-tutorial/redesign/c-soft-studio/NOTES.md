# Direction C: Soft Studio

Open it at `http://127.0.0.1:8765/redesign/c-soft-studio/`. This is a mockup for owner review, not app code.

**Concept.** The whole module lives inside the mascot's own palette: blush coat, cocoa mane and cream paper. One cool periwinkle marks everything you can press. A pastel "studio band" runs across the top and ends in a gentle wave. Inside it sits a storybook deck: five tilted step cards (Team, Event, Your list, Results, Ask for more), and Bree walks along their top edge to the current step. Each view has one headline and one sentence. Everything else opens on demand (hints, weights, past events, the profile card). Bree carries the states the old mockup handled with text: waiting, loading, gentle errors, success and "you're done".

## Files

| Path | What it is |
|---|---|
| `index.html` | Markup for 6 screens, the review bar, the tour layer and an SVG icon sprite |
| `studio.css` | Tokens (light and dark), components, responsive rules and reduced motion |
| `studio.js` | Plain script with no libraries: 300 fictional profiles, ranking, tour, states and deep links |
| `screenshots/` | 19 at 1440×900 (1 full-page) and 7 at 390×844 (2 full-page) |

- Weight: 115 kB raw, about 29 kB gzipped (html + css + js).
- External requests: Google Fonts only (Fredoka 500/600, Nunito 400/600/700/800).
- Art: the 10 existing `.webp` files, referenced from `../../mockup/assets/`. None are copied.

**Deep links:**

- `?screen=team|event|build|compare|results|ask`
- `&team=4`
- `&results=locked|open|running|done`
- `&ask=1..3&asked=1|done`
- `&askerr=1`, `&nudge=1`, `&zero=1`: error states
- `&step=1..7|none`: tour
- `&theme=dark`, `&rm=1`

## Palette

Tokens are defined on `:root` and redefined for dark mode under `prefers-color-scheme` and `[data-theme="dark"]`. No CPP green or gold is used anywhere. The only green on screen is Bree's polo.

| Token | Light | Dark | Role |
|---|---|---|---|
| `--page` | `#FBF5EF` | `#1C1513` | Cream paper |
| `--surface` | `#FFFCF9` | `#271E1B` | Card stock |
| `--sunk` | `#F4EAE2` | `#332824` | Wells, tracks, rank chips |
| `--band` / `--wash-blush` | `#FCE3DE` | `#3A2522` | Studio band, blush plates |
| `--wash-peri` | `#E7E9FC` | `#262A48` | Periwinkle plates |
| `--wash-peach` | `#FDEBD6` | `#3A2B1C` | Peach plates, "seats still empty" row |
| `--ink` | `#3A2520` | `#F8EEE9` | Cocoa text |
| `--ink-soft` | `#6B5048` | `#CDB9B0` | Secondary text |
| `--accent` | `#4F5BD5` | `#A7B0FF` | Periwinkle: every interactive fill |
| `--accent-ink` | `#3C47B5` | `#B8C0FF` | Periwinkle text |
| `--accent-tint` | `#E7E9FC` | `#2E3358` | Selected rows, "on both" wash |
| `--rose` | `#A8453F` | `#F2A69C` | Gentle-error text |
| `--cocoa` | `#7A4A3A` | `#C99A86` | "Already coming" seats |
| `--blush` | `#EE9A90` | `#C9766D` | Decorative only (squiggle) |
| `--line` / `--line-strong` | `#EBDDD4` / `#A08378` | `#43352F` / `#8E776E` | Decorative divider / control outline |

### WCAG contrast (computed)

| Pair | Light | Dark |
|---|---|---|
| ink on page | 13.25 | 15.78 |
| ink on surface | 14.02 | 14.29 |
| ink-soft on page | 6.77 | 9.57 |
| ink-soft on surface | 7.17 | 8.67 |
| ink-soft on band | 5.99 | 7.61 |
| on-accent on accent (buttons) | 5.54 | 8.83 |
| accent-ink on accent-tint | 6.32 | 6.95 |
| accent-ink on surface | 7.44 | 9.34 |
| rose on wash-blush (errors) | 4.79 | 7.30 |
| ink on wash-peach | 12.30 | 11.93 |
| line-strong on page (UI, needs 3:1) | 3.23 | 3.89 on surface |
| cocoa seat on surface (UI) | 7.16 | 6.56 |
| accent seat on surface (UI) | 5.42 | 8.00 |
| review bar text | 14.23 | 16.90 |

All text pairs pass AA. Blush is never used for text.

## Type

- **Fredoka 500/600** is the display face: headings, numerals, buttons and the deck. It is rounded and friendly, but it stays geometric enough to read as tech.
- **Nunito 400–800** is the body face: humanist, with rounded terminals and tabular numerals for counts and weights.
- Headlines run at 44px (60px on the opening screen) with -0.02em tracking. Body is 18px. Nothing that carries data is under 14.5px.

## Layout principles

1. **One focal point per view.** Each view has one headline, one sentence, and one primary action in periwinkle.
2. **Storybook deck as navigation.**
   - The five steps are cards, tilted ±1.3°. The current card is straight, raised and filled in periwinkle.
   - Finished cards get a check badge.
   - Bree walks to the current card: a transform slide with a hop, and she flips to face the direction she is walking.
3. **Rail for the mascot (Duolingo-like).** On desktop, secondary content sits in a 300px right rail: an art plate plus a hint that opens on demand. At 390px the rail stacks below the content.
4. **On demand, not on screen.** These are all closed until asked for:
   - saving weights
   - the weights inside each saved setting
   - the ten past events
   - a person's major and year (tap the row)
   - the profile card preview
   - the "What will we see?" hint
5. **States are illustrated, not written.** Locked, loading, empty, error and done each get a pose instead of a paragraph.
6. **Check bar for choices.** "Asking for more" uses a Duolingo-style bottom bar:
   - it turns blush with the surprised face for "Pick one way first."
   - it turns periwinkle with the laughing face once the team has asked
   - keys 1–3 pick an option
7. **Soft, never childish.**
   - Card radii are 16px. Mascot plates are 28px.
   - Shadows are wide, soft and cocoa-tinted.
   - Buttons have a 3px inner lip so they feel pressable, without a hard offset shadow.
   - There is no emoji and no confetti.

## Clutter cut: visible text blocks per screen

**Method.**

- A script counts every visible leaf text block inside the visible screen section.
- Closed disclosures, screen-reader-only text and persistent chrome are not counted. Chrome means the old brand and ribbon, and the new band and footer.
- "Data" means list rows, tables, the seat grid and team tiles.
- "Before" is `mockup/index.html` on the same deep links.

| Screen | Before: copy blocks / words | After: copy blocks / words | Data blocks, before → after |
|---|---|---|---|
| Team entry | 6 / 65 | **5 / 46** | 6 → 6 |
| Event picker | 13 / 86 | **11 / 41** | 0 → 0 |
| Weights + list | 19 / 129 | **23 / 87** (16 without the new "Who is on the list" block) | 72 → 61 |
| Save + compare | 20 / 135 (inside the matching screen) | **18 / 53** | 81 → 130 (two full 30-name lists side by side) |
| Results, locked | 5 / 35 | **5 / 22** | 0 → 0 |
| Results, after the run | 11 / 52 | **10 / 40** | 0 → 14 (the required "email everyone" table) |
| Asking for more | not in the old mockup | 13 / 64 | 0 |

- **Per list row:** 6 visible fields → 4 (rank, name, marker, reason). Major and year open on tap.
- **Rows shown by default:** 12 → 10, with "Show all 30".
- **Words of copy across the five comparable screens:** 407 → 249 (−39%).
- **Where the count went up:** weights + list gained the "Who is on the list" table, which the old mockup lacked and the requirements demand. Results gained the "email everyone" table for the same reason.

## Pose-to-moment map

| Art | Moment | Where it appears |
|---|---|---|
| `pose1-guide` | Welcome | Opening-screen hero (waves on arrival); tour step 1; the deck walker; results "open, ready to run" |
| `pose2-chill` | Idle / waiting | Results locked ("Results are closed"); tour step 3 ("Follow the path") |
| `pose3-explore` | Empty states, exploring | Event-picker rail; empty saved slot ("Slot 3 is free"); tour steps 2 and 5 |
| `pose4-worker` | Loading | "Re-sorting" chip over the list while it rebuilds; results "Sending 30 invitations…" with shimmer seats; tour step 4 |
| `pose5-celebrate` | Success | Results reveal (hops as the seats fill); tour finish |
| `face1-happy` | Small success | "Saved as …" toast |
| `face2-surprised` | Gentle error | No team picked; all weights at 0 (overlay on the dimmed list); no way to ask chosen |
| `face3-curious` | Thinking, hints | "Which one first?", "What will we see?", the "Nobody on this list is …" note, tour step 6 |
| `face4-laugh` | You're done | Check bar after asking; "Round one is done" screen |
| `face5-calm` | Always here | Tour launcher; "Who is on the list" header; "Tour closed" toast |

## Functional parity checklist

- **Flow:** team entry (radio group, arrow keys) → event picker → weights + ranked list.
  - The list shows the "how much we know" marker (icon plus words, three states) and the reason line.
  - The weights card shows "Total weight: 1.00" and "What matters is how the weights compare…".
  - "Who is on the list" counts the list by major, year and how much we know, next to all 300. Counts only.
  - Download, save, and compare two settings with shared names marked.
  - Results: locked → open → running → done. The seat chart keeps "already coming" separate from "came from your list", and the table shows invited, signed up, came and seats still empty next to "email everyone".
  - Asking for more has 3 choices, each with one plain sentence and no numbers, then a profile refresh and "Round one is done".
- **Tour:** 7 steps with a spotlight and click blockers.
  - Next, Back, Skip, Esc, and ← / → keys.
  - Tab stays inside the card, focus moves to the step title, and each step is announced in a live region.
  - "Don't show this again" is stored per browser in `localStorage`.
  - Reduced motion (OS setting or simulated) removes all movement.
  - At 390 the card becomes a bottom sheet, with Bree peeking over it.
- **Notices:**
  - Fictional-data line in the footer of every screen.
  - License line on the opening screen.
  - No percentage, score or confidence anywhere (ADR-0025).
- **Reviewer switcher:** screens 1–6, plus Review controls (results state, simulated reduced motion, replay tour, forget "seen", light/dark).

## Deviations to flag

- **Default weights are 0.25 each**, per the requirements (OQ-CE-02). The old mockup used 0.40 / 0.25 / 0.25 / 0.10.
- **The 300 profiles are generated** from a fixed seed with realistic mixes (about 70 cards, about a third attended). They are illustrative, not Ann's file.
- **The periwinkle accent follows the brief.** It overrides the taste skill's "no purple" rule. It is kept on the blue side and never glows.
- **Asset crops show strays.** `face4-laugh.webp` has a stray mark on its left edge, and `pose3-explore.webp` has a stray tail blob. Both come from the sheet crops.

## Three things to refine next

1. **Art.**
   - Re-crop `pose3` and `face4` to remove the neighbour-tile strays.
   - Commission 2 poses from `IMAGE-PROMPTS.md`: a side-view walk for the deck walker, and a sheepish pose for errors, so errors stop borrowing a face.
2. **Round two and instructor.**
   - Design the round-two results: round one next to round two, next to "email everyone".
   - Design the instructor page in this language, since both are still out of scope here.
3. **Projector pass.**
   - Test at 1280×720 and 1024 wide at 150% zoom, where the reason line (14.5px) and the deck labels are the risks.
   - Self-host subset fonts so a classroom PC makes no third-party request.
