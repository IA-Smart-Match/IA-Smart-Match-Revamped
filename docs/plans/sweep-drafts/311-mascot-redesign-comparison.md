> DRAFT — needs Danny decision. Nothing here is decided.

# #311 — Mascot tutorial and redesigns A / B / C: comparison

## Verified facts
- The mockups are on `main`, not only `Frontend-Experimental`: commit `10537a48` ("add mascot tutorial and three class-exercise redesign mockups") is an ancestor of `origin/main` (`git merge-base --is-ancestor`, true) and is also on `origin/Frontend-Experimental`. The issue text and the README line 3 ("on the `Frontend-Experimental` branch") are stale.
- Static HTML/CSS/JS only, nothing imported by `apps/` (`docs/design/class-exercise/mascot-tutorial/README.md:3-5`). Mascot art is shared from `mockup/assets/` (10 webp files) in all three.
- 2D "Bree" chosen over 3D; 3D dropped (`README.md:34`; `PLAN.md` §2, §8 Q2: 3D would add 16-24 h).
- The real exercise UI is in `apps/web/legacy-frontend/src/app/pages/exercise/` (`ExerciseScreen.tsx`, `ExerciseEntry.tsx`, `ExerciseResults.tsx`, etc.) with styles `src/styles/exercise.css` and `exercise-motion.css`. All redesign work would land there.
- Size on disk (incl. screenshots): A 2.9 MB, B 3.0 MB, C 4.5 MB. Code: A `app.js` 554 + `styles.css` 524 + html 350 lines; B 596 / 519 / 244; C `studio.js` 526 + `studio.css` 571 + html 387.

## Comparison (sources: each `NOTES.md`)
| | A Playful Learning | B Friendly Tech | C Soft Studio |
|---|---|---|---|
| Tone | Duolingo-style lesson path, chunky pressable buttons | Calm product (Linear/Arc register) with a Duolingo shape | Storybook deck, pastel studio band |
| Palette | Violet primary `#5B3DF5`, coral accent, sky secondary (A NOTES Palette) | Slate ink, one electric blue `#2D5BFF`, pink highlight `#FF7AA2` | Cream `#FBF5EF`, cocoa ink, periwinkle `#4F5BD5` accent |
| Fonts | Fredoka + Nunito | Sora + Geist | Fredoka + Nunito |
| Navigation | Top progress path, 6 steps, fixed bottom action bar | Left step rail (segmented bar at 390), sticky action bar | 5 tilted step cards; Bree walks to the current card; 300 px right rail |
| Mascot use | Bree on every screen, speech bubble, pose per moment | Companion panel + pose per moment; calmer, error is a surprised face | Largest role: hero, deck walker, plates, bottom-sheet peek on mobile |
| Screens | 8 (Team, Event, Weights+list, Compare, Results closed/open, Ask, Done) | 6-step flow incl. Asking, done, compare, results locked/open/run | 6 (team, event, build, compare, results, ask) with results locked/running/done |
| States covered | Error, empty, loading, tour, yay band | Error, empty compare, loading skeleton, asking confirm, tour | Error, zero-weight, running, ask error, nudge, tour |
| Dark mode | Yes, follows OS; review toggle | Yes | Yes (OS or `data-theme`) |
| Mobile (390) | 4 screenshots (team, weights, results, tour) | 4 screenshots | 7 screenshots (2 full-page); card becomes a bottom sheet |
| Contrast | All text pairs pass AA, most AAA (A NOTES) | All pass; pink decorative-only | All text pass AA; blush never text |
| Reduced motion | 150 ms fades; simulate toggle | Same, no bob/spring/shimmer | Removes all movement |
| Clutter cut (text blocks) | Weights+list 84 to 40; Compare 94 to 41 | Weights+list 91 to 50; Compare 101 to 67 | Has a clutter table (`NOTES.md:105`), numbers not reproduced here |
| Weight (html+css+js) | 112 kB raw / 28 kB gz (js listed) | not stated | 115 kB raw / ~29 kB gz |
| Convention conflicts flagged | Violet vs "no AI purple"; hard-offset button edge; sparks vs "no confetti" (`DESIGN.md` §4/§10) | Brief pinned; spring easing and shimmer kept on purpose | Periwinkle vs "no purple"; asset strays; **uses 0.25 default weights (stale)** |
| Biggest known gaps | Weight total below fold; round two not designed; art needs 2x | Mobile sticky weights; round two; projector contrast | Round two; instructor page; re-crop art |

Note: all three predate the 3/3/2/2 whole-number defaults (Ann 2026-10-06; `docs/decisions/class-exercise-default-weights-2026-10-06.md`). C explicitly says 0.25 (`c-soft-studio/NOTES.md`, Deviations). A and B `app.js` also contain "0.25" strings (4 and 5 hits; not inspected).

## Build cost into apps/web
No per-direction estimate exists. The only estimate is `PLAN.md` §7: phases 1-6 = 27.5-35.5 h for 2D tour (vite build/static serving 4-6 h, tour core 10-12 h, 2D mascot 4-5 h, tests 4 h, effects 3-6 h, classroom check 2 h); 3D adds 16-24 h. That covers the tour/mascot, not a full visual redesign. Reskinning every exercise screen is extra and unestimated here. `PLAN.md` also recommends doing the vite build and moving recharts (104 kB gz) behind the results route first, as it is independent of the mascot.

## What graduating each would touch (all under `apps/web/legacy-frontend/src/`)
| | A | B | C |
|---|---|---|---|
| Tokens/CSS | New violet/coral tokens in `styles/exercise.css`; chunky button style | New blue/slate tokens; rail layout | New cream/cocoa tokens; deck + band components |
| Pages | Restructure to 8 one-question screens (`ExerciseEntry`, `ExerciseEventPicker`, `ExerciseMatching`, `ExerciseResults`, `ExerciseAskingForMore`) | Left-rail shell around same pages; sticky bar | Deck shell + right rail; heaviest layout change |
| Tests | Many existing `*.test.tsx`/layout tests assume current DOM | Same | Same |
| Fonts | 2 Google families (self-host in prod) | 2 families (Sora, Geist) | 2 families |
| Assets | 2x Bree exports; pointing pose | same | same + walk and sheepish poses |
| Docs | `DESIGN.md` exceptions for mascot, tint, star burst (`PLAN.md` §8 Q4) | same, fewer | same |
Common prerequisites: `PLAN.md` §8 open questions (mascot name vs Billy the Bronco, preview by Dr. Wang/Dr. Lin/Ann, seen-state scope), and an `apps/web/DESIGN.md` update.

## Option 0 — do none
Keep the current exercise UI (already redesigned as "the invitation desk," PRs #245-#251 per `docs/plans/backlog.md`). Leave the mockups as reference on main. Pros: zero cost and risk before Oct 16 (test-pass date in #293). Cons: no mascot tour; mockups stay unreviewed by Ann/Dr. Lin.

## Open questions
1. Which direction graduates, or none? — Danny (Ann / Dr. Wang / Dr. Lin preview is `PLAN.md` §8 Q3; Danny decides whether to show them).
2. Is a tour-only graduation (mascot overlay on the existing UI) acceptable instead of a full reskin? — Danny.
3. Mascot name and `DESIGN.md` exceptions (`PLAN.md` §8 Q1, Q4). — Danny.
4. Update README line 3 and mockup defaults (3/3/2/2) before any show-and-tell? — Danny.
5. Timing relative to Oct 16 and the 20 Nov CBACH decision. — Danny.
