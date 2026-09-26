# Experiments — directions explored for the class exercise refresh

**Recommendation:** ship **"The invitation desk"**: CPP brand material
(Eggwhite page, white card stock, CPP Green ink, Gold as a single
highlighter) with **Fable's seating chart ("The Room") as the one
recurring picture, on the results screens only**, and **the Ledger's
headline sentence and ruled figures band** for the results payoff.
[`DESIGN.md`](DESIGN.md) is written to this direction.

Inputs (both arrived 2026-09-25):

| Input | What it gave | Where it is folded in |
|---|---|---|
| Fable experimental designer | 4 directions, a 3-reviewer adversarial pass, 12 PNG mock-ups, image-gen seeds | This file; 8 PNGs in [`assets/mockups/`](assets/mockups/); DESIGN.md 6.12, 6.15, 7.1 |
| Sonnet library scout | 10 library categories, a motion spec, 8 SVGs, 12 references | [Library picks](#library-picks) below; DESIGN.md 4 and 5; 7 SVGs in [`assets/svg/`](assets/svg/) |

## 1. Fable's four directions

| Rank (Fable) | Direction | Idea | Mock-ups |
|---|---|---|---|
| 1 | **The Room** | Every screen shows the 60-seat room; the list reserves chairs; results show who sat down | [list](assets/mockups/room/list-1280.png), [compare](assets/mockups/room/compare-1280.png), [results](assets/mockups/room/results-1280.png) (+ 390 each) |
| 2 | **The Ledger** | Editorial broadsheet: masthead, numbered column, a front-page headline sentence on results | [results](assets/mockups/ledger/results-1280.png), [results 390](assets/mockups/ledger/results-390.png) |
| 3 | **Corkboard** | Profiles as index cards under four dials; compare joined by red string | none |
| 4 | **The Reveal** | Dark game-show stage, tile flips, a seat counter | none (deliberately risky) |

## 2. Adversarial findings (Fable's review, condensed)

Reviewers: the instructor (50 minutes, an untested projector in a lit
room), a student on a 390px phone with weak Wi-Fi, and an accessibility
reviewer (VoiceOver, reduced motion, contrast).

| Direction | Instructor | Phone | Accessibility | Fails in class when |
|---|---|---|---|---|
| The Room | medium: "is that the actual room?"; room pushes the list below the fold | medium: list starts ~900px down; thumbs must be 44px | low once done: shape not hue; room `aria-hidden` | seat count is not 60, or the room hides the list |
| The Ledger | medium: hairline rules and 400-weight serif wash out | medium: compare loses side-by-side | low: best of four | the projector washes out thin rules |
| Corkboard | **high**: reads as a kids' app; cork halves contrast | **high**: 30 cards = 6,000px scroll; dials worse than sliders | **high**: string is visual only; texture fails contrast | always, on phones |
| The Reveal | **high**: 4s × 6 teams × 2 rounds of class time; dark UI in a lit room | **high**: faders on touch; reason hidden behind a tap | **high**: colour-coded state, motion as the product | the room is lit (it will be) |

## 3. My own review of the Room and Ledger mock-ups

What they get right: the room makes "46 seats are still open" countable;
the seat sentence set large is the lesson's "so what"; warm paper beats
slate; the 390 compare with "Showing 10 of 30" works.

What this system changes, and why:

| Mock-up choice | Change | Reason |
|---|---|---|
| Teal `#2F6F73`, Fraunces / Newsreader, black buttons | CPP Green, Transducer / Proxima Sera / Usual, green primary | Brand is fixed (`apps/web/DESIGN.md`); Ann's build table says no new colours or styling beyond what exists |
| Six team colours | None | New hues; team identity is the number |
| Room on the matching screen: "30 of 60 chairs reserved" | Room only on results | An invitation is not a seat. Showing invites as reserved chairs teaches the wrong model and pre-empts the result |
| Room on results: invited = outline, signed up = half, attended = solid, inside the 60 seats | Seats = sign-ups only: already coming, your invitations, still open. Attendance lives in the chart | Matches the server's `event_seats`, `existing_signups`, `team.signed_up_count`, `seats_empty` exactly; no seat stands for a person who never signed up |
| "How much we know" as 1–3 filled dots | Icon + words chip | A 1–3 dot scale reads as a rating of the person |
| Reason in a separate "Why" column | Reason under the name | Read name then why; survives 390 without a column |
| Uppercase eyebrow "SMARTMATCH · CLASS EXERCISE · …" | Removed | Parent contract bans a category label above the `h1` |
| Ledger headline "Your list filled 6 seats." | Not used; the three-line seat sentence is the headline | One sentence pattern, fixed by the brief; avoids a claim of credit |
| Ledger 2px rules idea | Kept for the figures band | Survives a washed-out projector |
| Stat tiles (Room) | Ruled figures band (Ledger) | Avoids the hero-metric card template |
| Two rooms side by side for round two | One room (round two) + the line "In round one your team's list left 46 seats empty." + a three-group chart | One picture per projector view |
| Corkboard red string | Optional "Variant B" connector lines, desktop compare only, off by default | Worth testing; clutters at 30 rows |
| Reveal's row-by-row fill | Kept as `ce-seat-fill`, ≤1.8s, with a Skip and a reduced-motion final state | The only moment that earns choreography |

Mock-ups also used a major, "Marketing Management", that is not in the
data file's vocabulary. The prompt pack uses the six real majors.

## 4. Recommended direction and why

**The invitation desk** (DESIGN.md sections 2–7):

1. **It answers "barebone and industrialized" with material, not
   decoration.** Card stock on eggwhite, a serif voice for headings and
   reason lines, and a real slider replace grey outlined boxes, without a
   new colour.
2. **The payoff has a picture that is also the data.** 60 seats, filled in
   the order that tells the story, then one plain sentence. The class can
   count the empty seats from the back row.
3. **It stays credible.** No confetti, no game-show, no handwriting, no
   rating dots. It reads as a marketing tool a professor would put on a
   projector.
4. **It keeps every rule the code already enforces:** counts not scores,
   server sentences verbatim, unknown never drawn as zero, calm refusals.
5. **It survives the adversarial cases.** Lit room (light default, ≥4.5:1
   text), phone (sticky weights bar, list as cards), reduced motion (every
   motion has a stated fallback), screen readers (room `aria-hidden`,
   sentences announced once).

Runner-up: the pure Ledger. It is the most accessible and the calmest, and
it would be a good fallback if the seating chart tests poorly with Ann and
Dr. Lin. Its type ideas are already in the recommendation.

Not recommended: Corkboard and The Reveal, for the reasons in section 2.

## 5. What to test in the November practice run

1. Can a volunteer at the back row read the seat sentence and count the open seats?
2. Do teams read the reason line before the marker chip?
3. Does the sticky weights bar on 390 get used, or do phones stay on laptops?
4. Does the 1.8s reveal feel like evidence or like a game? (Kill switch: the revisit state.)
5. Does "Variant B" connector-line compare help, or clutter?

## Library picks

From the Sonnet scout (`libraries.md`), verified against
`apps/web/legacy-frontend/package.json` on origin/main.

| Need | Pick | Installed | Note |
|---|---|---|---|
| Primitives | Radix UI | yes | Keep |
| Motion | `motion` 12.23.24 | yes | `layout` for re-order, `animate()` for counters |
| Page transitions | View Transitions API | browser | Progressive; no-op where unsupported |
| Charts | Recharts 2.15.2 | yes | Restyle only; keep the table fallback |
| Icons | `lucide-react` 0.487 | yes | One set; `@iconify/react` not used here |
| Slider | `@radix-ui/react-slider` 1.2.3 | yes | **Correction:** the scout says `WeightsControls.tsx` already uses it. On origin/main it does not; the weights are text inputs. The slider is new UI. |
| Toasts | Sonner | yes | Only for "saved"; never for refusals |
| Skeletons | Tailwind `animate-pulse` equivalent | yes | Use `ce-skeleton` timing |
| Confetti | `canvas-confetti` | yes | Deliberately unused |
| Fonts | Public Sans / Space Grotesk (scout) | n/a | Not adopted. Production keeps licensed faces; mock-ups use Archivo, Source Serif 4 and Figtree as stand-ins |

Scout SVGs: 7 of 8 adopted (tidied: dead element removed, font pinned on
`round-journey.svg` text, `hidden-truth.svg` renamed `partly-known-card.svg`
with a neutral label so no screen implies a hidden truth is revealed).
`seats-vs-signups.svg` is superseded by the live seating chart.

Scout references worth keeping for tone: Notion and Linear (restraint and
micro-interaction), Stripe (large numerals with whitespace), Material 3 data
visualisation (accessible series). Kahoot, Duolingo and Class Dojo mark the
ceiling of playfulness; this system stays below it.

## Image-generation seeds

Fable wrote one paragraph per mock-up for image models (kept in the Fable
scratch folder, not committed). Before reusing any: replace teal with CPP
Green `#005030`, remove the uppercase eyebrow line, replace "30 of 60 chairs
reserved" with no room on the list screen, replace dot markers with icon +
words, and use only the six majors in the prompt pack's shared data.
