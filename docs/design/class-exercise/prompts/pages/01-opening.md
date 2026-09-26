# Page 1 — opening screen with the license line

The first thing projected. It sets the task in one question, shows the
license line, and leads straight into team entry (page 2, same route).

- **Route:** `/exercise` (top zone). Code: `ExerciseEntry.tsx`.
- **System:** [`DESIGN.md` 7.1](../../DESIGN.md#71-opening-screen-exercise-top-zone), tokens 3.1–3.4, motion `ce-fade-rise`.
- **Asset:** [`lecture-hall.svg`](../../assets/svg/lecture-hall.svg) (desktop only).
- **Reference:** the headline question comes from Fable's Room mock-up, [`room/list-1280.png`](../../assets/mockups/room/list-1280.png).
- **Content:** h1 "Who should we invite?"; the license line verbatim; the ribbon sentence.
- **States:** ready, loading, refused, unreachable. The license line shows in all four.

## Google Stitch prompt

```text
Desktop web, 1280px. The opening screen of "Smart Match class exercise" for
a university business course. Warm eggwhite page #F8F6F1.

Top: a slim full-width ribbon, #FFF1CC background, 14px corners, info icon
in #7A5200, text 16px #163229: "All student profiles are fictional, shaped
by overall survey percentages."

Below, a small horizontal Cal Poly Pomona wordmark placeholder at top-left
(a grey rectangle labelled "CPP logo", 160x40; do not draw a logo).

Main area, two columns (7/5), generous whitespace (96px above the title):
Left: a large title in Archivo SemiExpanded 600, 48px, #163229: "Who should
we invite?". Under it, Figtree 22px #59665F, max 60 characters per line:
"Your team is promoting a campus career event with 60 seats. Choose whom to
invite, see what happened, then try again." Below that, a quiet #F2EEE8
panel (14px corners, no shadow, 16px padding) holding the license line in
Figtree 18px #163229: "For California State Polytechnic University,
Pomona — College of Business Administration instructional use only. All
student profiles are fictional."
Right: a simple geometric line pictogram of a lecture hall (a roof line over
two rows of small rounded squares, three of them faded), 160px, in CPP
Green #005030. No people, no photo.

Below both columns, the start of the next section: a heading "Which team
are you?" in Source Serif 4 32px (content continues on the next screen).

No kicker text above the title. No icon beside the title.
```

**390 follow-up:** "Make this a 390px mobile screen: single column, 16px
side margins, title 32px, hide the lecture-hall pictogram, license panel
full width directly under the lead line."

## Claude Design prompt

```text
Build the opening zone of /exercise for the Smart Match class exercise with
the preamble tokens. It is the top of the same page as team entry (page 2);
render the "Which team are you?" h2 at the bottom so the join is visible.

Structure:
- Ribbon (see preamble).
- Header row: CPP horizontal logo placeholder (a 160x40 box labelled "CPP
  logo — use BrandLogo.tsx"; never draw or recolour the logo).
- Hero grid 7/5 at 1280 with 96px top padding:
  h1 "Who should we invite?" (--ce-font-display 600 48/56).
  Lead (body 22/34, --ce-ink-muted, max-width 60ch): "Your team is
  promoting a campus career event with 60 seats. Choose whom to invite, see
  what happened, then try again."
  License panel (--ce-surface-sunk, --ce-radius-card, no shadow, 16px
  padding, body 18/28): "For California State Polytechnic University,
  Pomona — College of Business Administration instructional use only. All
  student profiles are fictional." Mark it data-slot="exercise-license-line".
  Right column: ../../assets/svg/lecture-hall.svg at 160px in --ce-primary,
  aria-hidden (decorative).

Motion: on first load, the lead and license panel use ce-fade-rise (240ms,
--ce-ease-out, 60ms apart). The h1 is visible immediately (no fade on the
title). Reduced motion: 150ms opacity only.

States for the switcher: Ready · Loading (the hero renders at once; below
it, six skeleton team tiles; hidden status "Loading the exercise…") ·
Refused (a calm notice under the hero with the server's sentence, e.g. "The
instructor has not loaded the student body yet.") · Unreachable (problem
notice "The exercise could not be reached. Check the connection and try
again." with "Try again"). The license panel is present in every state.

390: single column, h1 32/38, lead 18/28, illustration hidden, license panel
full width.
```

## Review checklist

1. The license line is verbatim and visible in every state and width.
2. The data wording is only the ribbon sentence.
3. No eyebrow, no icon next to the h1, no logo drawn by the tool.
