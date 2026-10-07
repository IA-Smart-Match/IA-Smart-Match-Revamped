# Smart Match CPP — three mockup proposals for the CBACH advisory board

**Date:** 2026-10-06 · **For:** the board presentation on Thursday 2026-10-08
(Chau and Janice presenting; about 15 minutes of front-end demo, then Q&A) ·
**Branch:** `demo/cbach-advisory-2026-10-08` · **Status:** proposals for owner and
Dr. Wang review. Not app code; nothing under `apps/` changed.

Dr. Ann Wang sent a clickable front-end prototype on 2026-10-06 with the note
"Feel free to use it and modify it from your end." These are three team
proposals built from it. Each shows the same screens, the same wording, the same
300 made-up profiles and the same ranking; they differ in look, layout and
motion.

## Open them

Double-click an `index.html`, or serve this folder and open the links:

| Proposal | File | Two-second read |
|---|---|---|
| **A · Blueprint** | `mockups/a-blueprint/index.html` | Dr. Wang's green-and-white pages with a left menu, made exact |
| **B · Workbench** | `mockups/b-workbench/index.html` | A grey, full-height workspace with a sidebar and dense tables |
| **C · Walkthrough** | `mockups/c-walkthrough/index.html` | Warm paper, serif headlines, a green stop rail along the bottom |
| Her original | `source/SmartMatch_CPP_Prototype_10062026_1.html` | For comparison; never edit |

To serve: `python3 -m http.server 8790` in this folder, then
`http://localhost:8790/mockups/a-blueprint/index.html` (and `b-workbench`,
`c-walkthrough`).

In each: **PageDown / PageUp** step through the nine demo stops; **Presenter
guide** shows who presents each screen, what to click and what to say; **Reset
demo** starts over. In B, **Ctrl/⌘+K** switches portal.

## What is in this folder

| Path | What |
|---|---|
| `source/` | Dr. Wang's prototype and README, unmodified, with `PROVENANCE.md` |
| `reference/` | 32 screenshots of her prototype |
| `DESIGN.md` | The shared contract all three follow (content and exact copy, data, wording, spacing, type, colour with contrast numbers, components, motion, accessibility, engineering rules, audit checklist) and the three direction specs |
| `shared/data.js` | Her data and matching logic, extracted without changing values; all three load it, so they rank identically |
| `shared/vendor/` | GSAP 3.15.0 (core and Flip) and six font families, stored locally so the demo needs no internet |
| `mockups/<letter>-<slug>/` | `index.html`, `styles.css`, `app.js`, `NOTES.md`, `screenshots/` |
| `audit/` | The independent UI audit (`AUDIT.md`), once it has run |

## The three proposals

### A · Blueprint — recommended lead

Her layout, palette (Cal Poly Pomona green and gold) and fonts (Bricolage
Grotesque, Public Sans), made precise: one spacing scale, legible sizes for the
back row, visible focus, messages that stay on screen.

- **Why lead with it:** she will recognise it as hers, her presenter guide
  carries over unchanged, and it is the safest to have complete by Thursday.
- **Best screen:** the student interview.
- **Risk:** it can read as "the same thing".
- **Known gaps:** the Match table shows 5 full rows at 1440×900 where the spec
  asked for 6; re-ranking can drop a frame on a slow machine.

### B · Workbench — alternate

A calm, dense workspace in the lineage of mature productivity tools: persistent
sidebar, Ctrl/⌘+K portal switcher, split panes, a dark theme (Instrument Sans,
JetBrains Mono).

- **Best screen:** Match students to an event — 10 rows visible at 1440×900, and
  the list re-ranks smoothly when a weight moves.
- **Risk:** it looks finished, which works against "design for the next phase";
  type is smaller from the back row.
- **Known gaps:** re-ranking misses the frame budget on a slow machine in some
  runs.

### C · Walkthrough — alternate

Presentation-first: warm paper, serif headlines (Source Serif 4, Figtree), one
idea per first screenful, and a stop rail with "Stop n of 9", Back and Next that
carries the 15-minute story.

- **Best screen:** the entry and the Grace Delgado story (the "#4" callout on
  the Match screen).
- **Risk:** the most custom layout, so the most to check.
- **Known gaps:** one screen clears the fold by 3 pixels at 1440×900.

The team's mascot Bree is not used in any of the three; DESIGN.md §14.7 gives
the reasoning for a board audience.

## What all three share

- **Her wording, verbatim.** The only added strings are ten small ones listed in
  DESIGN.md §2.13 (for example the marker "Design for the next phase — made-up
  data" and "Scripted for this demo. Not a live AI.").
- **Her honesty rules:** every screen keeps its working / planned label; the
  interview and the CBACH assistant are labelled as scripted; only the 300
  made-up profiles appear.
- **Default weights 3 / 3 / 2 / 2 on whole-number sliders from 0 to 10** — the
  ruling recorded in `docs/decisions/class-exercise-default-weights-2026-10-06.md`
  (PR #349).
- **Identical ranking.** For Northline at the default weights after the
  interview, all three show Emeka Soto, Camila Alcantar, Mei Huynh, then Grace
  Delgado at #4.
- **Three small logic fixes** to her prototype (DESIGN.md §3.7): the profile-card
  count reads 71 after the interview, not 72; "Graduate school" is stored as
  itself; one career-points total on all screens.
- **No network:** GSAP and fonts load from `shared/vendor/`.

## Things in her prototype to raise with her before Thursday

Not changed in the mockups; her wording is kept. Full list in DESIGN.md §2.15.

1. An interview line says "consulting and technology"; the picks on the guided
   path are technology and entertainment.
2. The Career Hub screen is about to invite students to the Mar 4, 2027 talk
   while the Partner screen already reports its results.
3. Her page turns dark when the laptop is in dark mode.
4. Her focus ring is gold on white (contrast 1.75:1), and outcomes show only as
   a 2.3-second toast.

## Verification so far

Each builder ran the DESIGN.md §11 checklist on its own mockup (results in each
`NOTES.md`): A 59 of 60, B 58 of 60, C 58 of 60. Those are self-reports. An
independent audit of all three is recorded in `audit/AUDIT.md` when complete;
treat its verdicts as the authority.

Not yet checked by anyone: a real projector, the presenting laptop, Edge or
Firefox, and a screen reader.

## Decisions needed

| # | Question | Recommended |
|---|---|---|
| 1 | Which proposal goes on the projector Thursday | A, with B and C shown as alternates if time allows |
| 2 | Apply the five proposed wording changes (DESIGN.md §2.14) | No, unless Dr. Wang agrees |
| 3 | Keep GSAP in the repository (free of charge, not open source; licence note in `shared/vendor/gsap/LICENSE.md`) | Yes |
| 4 | Her "match 6 of 10" and readiness percentages conflict with the class exercise's no-scores rule | Keep hers in the mockups; settle before the real build |

## After Thursday

Per her README, the real build starts after the teaching module is finished
(2026-10-30) and only once the college gives the go-ahead, one workflow at a
time: student records, CPP login, then matching students to one event.
DESIGN.md §10.3 maps each mockup component to the app's React and Radix
components for that port.
